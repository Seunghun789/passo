"""홈 · 대시보드 · 자동화 API. 확정 지식은 부른 사람의 JWT 로만 읽고(RLS), 숫자는 core/engine 이 센다.
켜기 · 올리기는 화면이 보낸 규칙을 믿지 않고, 서버가 확정 지식에서 다시 만든 같은 제목의 규칙만 넣는다."""
import asyncio
import json
import os
import time
from typing import Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

PERIOD = Query('이번 주', pattern='^(오늘|이번 주|이번 달|올해)$')


class Pick(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    title: str = Field(min_length=1, max_length=200)


class AutomationStatus(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    status: Literal['켜짐', '꺼짐']


class WidgetStatus(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    status: Literal['올림', '내림']


def snapshot(g, token, tid):
    """확정 지식 K 와 자동화 · 지표 줄. 한 번 읽어 여러 카드를 센다."""
    from backend.ask import open_reader
    from core import engine
    t, http = open_reader(g, token, tid)
    try:
        K = engine.load(t)
        autos = t.get('automations', select='id,spec,status', order='id')
        widgets = t.get('widgets', select='id,spec,status', order='id')
        return t, K, autos, widgets, http
    except BaseException:
        http.close()
        raise


def read_failed(exc):
    print(json.dumps({'insights': 'failed', 'error_type': type(exc).__name__,
                      'read': str(exc) if str(exc).startswith('read_failed:') else None}), flush=True)
    return HTTPException(503, '기록을 읽지 못했어요. 잠시 뒤 다시 눌러 주세요.')


async def can_review(g, token, tid):
    return bool(await g.rpc(token, 'passo_access', {'tid': tid, 'operation': 'review'}))


def install_routes(app, session, gateway):
    async def run(g, token, tid, work):
        def job():
            t, K, autos, widgets, http = snapshot(g, token, tid)
            try:
                return work(t, K, autos, widgets)
            finally:
                http.close()
        try:
            return await asyncio.to_thread(job)
        except RuntimeError as exc:
            raise read_failed(exc) from None

    @app.get('/v1/workspaces/{tid}/home')
    async def home(tid: int, period: str = PERIOD, token=Depends(session), g=Depends(gateway)):
        """오늘 먼저 볼 것(걸린 자동화가 많은 순서로 두 장), 더 걸린 것 · 걸린 것이 없는 것, 보는 기간 한눈에."""
        await g.authorize(token, tid)
        from core import insights as ins

        def work(t, K, autos, widgets):
            on = [a for a in autos if a['status'] == '켜짐']
            cards = [{'id': a['id'], **ins.automation_card(K, a['spec'], period, detail=False)} for a in on]
            hit = sorted([c for c in cards if c['count']], key=lambda c: -c['count'])
            shown = [{'id': c['id'], **ins.automation_card(K, next(a['spec'] for a in on if a['id'] == c['id']), period)}
                     for c in hit[:ins.HOME_MAX]]
            return {'enabled': len(on), 'alerts': shown,
                    'more': [{'title': c['title'], 'count': c['count']} for c in hit[ins.HOME_MAX:]],
                    'quiet': [c['title'] for c in cards if not c['count']],
                    'glance': ins.glance(K, [w['spec'] for w in widgets if w['status'] == '올림'], period) if K['types'] else []}
        return await run(g, token, tid, work)

    @app.get('/v1/workspaces/{tid}/automations')
    async def automations(tid: int, period: str = PERIOD, token=Depends(session), g=Depends(gateway)):
        await g.authorize(token, tid)
        from core import insights as ins
        editable = await can_review(g, token, tid)

        def work(t, K, autos, widgets):
            _, rules = ins.suggestions(K, {a['spec'].get('title') for a in autos})
            return {'can_edit': editable, 'has_records': bool(K['types']),
                    'enabled': [{'id': a['id'], **ins.automation_card(K, a['spec'], period)} for a in autos if a['status'] == '켜짐'],
                    'off': [{'id': a['id'], 'title': a['spec'].get('title')} for a in autos if a['status'] == '꺼짐'],
                    'suggestions': [ins.suggestion_card(K, s) for s in rules]}
        return await run(g, token, tid, work)

    @app.post('/v1/workspaces/{tid}/automations', status_code=201)
    async def turn_on(tid: int, body: Pick, token=Depends(session), g=Depends(gateway)):
        """[켜기]: 지금 확정 지식에서 다시 만든 제안 중 같은 제목만 켠다."""
        await g.authorize(token, tid, 'review')
        from core import insights as ins

        def work(t, K, autos, widgets):
            _, rules = ins.suggestions(K)
            return next((s for s in rules if s['title'] == body.title), None)
        spec = await run(g, token, tid, work)
        if not spec:
            raise HTTPException(409, '제안이 바뀌었어요. 화면을 새로 열어 주세요.')
        return {'id': await g.rpc(token, 'passo_automation_add', {'tid': tid, 'rule': spec})}

    @app.post('/v1/workspaces/{tid}/automations/{aid}')
    async def automation_status(tid: int, aid: int, body: AutomationStatus, token=Depends(session), g=Depends(gateway)):
        """[끄기] · [다시 켜기]"""
        await g.authorize(token, tid, 'review')
        await g.rpc(token, 'passo_automation_status', {'tid': tid, 'aid': aid, 'next_status': body.status})
        return {'id': aid, 'status': body.status}

    @app.get('/v1/workspaces/{tid}/dashboard')
    async def dashboard(tid: int, period: str = PERIOD, token=Depends(session), g=Depends(gateway)):
        """확정한 종류마다 기록 수 · 숫자 칸 추이(저절로), 올린 지표, 추천 지표."""
        await g.authorize(token, tid)
        from core import engine, insights as ins
        editable = await can_review(g, token, tid)

        def work(t, K, autos, widgets):
            up = [w for w in widgets if w['status'] == '올림']
            picks, _ = ins.suggestions(K, {w['spec'].get('title') for w in widgets})
            cards = lambda specs: [c for c in (ins.widget_card(K, s, period) for s in specs) if c]
            return {'can_edit': editable, 'has_records': bool(K['types']), 'period': period,
                    'auto': cards(engine.auto_widgets(K)),
                    'widgets': [{'id': w['id'], **c} for w in up if (c := ins.widget_card(K, w['spec'], period))],
                    'down': [{'id': w['id'], 'title': w['spec'].get('title')} for w in widgets if w['status'] == '내림'],
                    'suggestions': cards(picks)}
        return await run(g, token, tid, work)

    @app.post('/v1/workspaces/{tid}/widgets', status_code=201)
    async def put_up(tid: int, body: Pick, token=Depends(session), g=Depends(gateway)):
        """추천 지표 [올리기]"""
        await g.authorize(token, tid, 'review')
        from core import insights as ins

        def work(t, K, autos, widgets):
            picks, _ = ins.suggestions(K)
            return next((s for s in picks if s['title'] == body.title), None)
        spec = await run(g, token, tid, work)
        if not spec:
            raise HTTPException(409, '추천이 바뀌었어요. 화면을 새로 열어 주세요.')
        return {'id': await g.rpc(token, 'passo_widget_add', {'tid': tid, 'rule': spec})}

    @app.post('/v1/workspaces/{tid}/widgets/{wid}')
    async def widget_status(tid: int, wid: int, body: WidgetStatus, token=Depends(session), g=Depends(gateway)):
        """[내리기] · 다시 [올리기]"""
        await g.authorize(token, tid, 'review')
        await g.rpc(token, 'passo_widget_status', {'tid': tid, 'wid': wid, 'next_status': body.status})
        return {'id': wid, 'status': body.status}

    @app.post('/v1/workspaces/{tid}/week-summary')
    async def week_summary(tid: int, token=Depends(session), g=Depends(gateway)):
        """[이번 주 요약 만들기]: 숫자는 engine 이 세고, Claude 는 그 숫자로 문장만 쓴다."""
        await g.authorize(token, tid)
        import anthropic
        from core import engine, llm, insights as ins
        usage, started = {}, time.monotonic()

        def work(t, K, autos, widgets):
            if not K['types']:
                return None
            with anthropic.Anthropic(**llm.connect(os.environ)) as client:
                lines, facts = engine.week_summary(t, llm.DEFAULT, K, api_client=client,
                    log_sink=lambda t, m, prompt, answer, used_in, used_out, started=None: usage.update(
                        model=m, prompt=prompt, answer=answer, input_tokens=used_in, output_tokens=used_out))
            out = []
            for line in lines:
                rows = engine.records_by_id(K, {f'r{i}' for i in line['ids']})
                out.append({'text': line['text'], 'evidence': ins.plain({
                    'columns': list(dict.fromkeys(k for r in rows for k in r if not k.startswith('_'))),
                    'rows': [{'id': r['_id'], 'values': {k: v for k, v in r.items() if not k.startswith('_')}} for r in rows],
                    'total': len(rows)})})
            shown = [{'name': f['이름'], 'now': f['이번 주'] if isinstance(f['이번 주'], str) else ins.fmt(f['이번 주']),
                      'before': f['지난주'] if isinstance(f['지난주'], str) else ins.fmt(f['지난주']),
                      'diff': ins.fmt(f['차이']), 'evidence': len(f['ids'])} for f in facts]
            return {'lines': out, 'facts': ins.plain(shown)}
        try:
            result = await run(g, token, tid, work)
        except anthropic.APIError as exc:
            print(json.dumps({'week': 'failed', 'error_type': type(exc).__name__, 'status': getattr(exc, 'status_code', None)}), flush=True)
            raise HTTPException(503, 'AI가 요약하지 못했어요. 잠시 뒤 다시 눌러 주세요.') from None
        if result is None:
            raise HTTPException(409, '아직 확정한 기록이 없어요.')
        if usage:
            price = llm.PRICE[usage['model']]
            cost = (usage['input_tokens'] * price[0] + usage['output_tokens'] * price[1]) / 1_000_000
            try:  # 사용 기록을 남기지 못해도 이미 받은 요약은 돌려준다
                await g.rpc(token, 'passo_log_ai', {'tid': tid, 'model': usage['model'], 'prompt': usage['prompt'],
                    'answer': usage['answer'], 'input_tokens': usage['input_tokens'], 'output_tokens': usage['output_tokens'],
                    'cost_usd': round(cost, 6), 'duration_ms': round((time.monotonic() - started) * 1000)})
            except (HTTPException, ValueError):
                print('{"week":"usage_log_failed"}', flush=True)
        return result
