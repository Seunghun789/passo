"""홈 · 대시보드 · 자동화 API. 확정 지식은 부른 사람의 JWT 로만 읽고(RLS), 숫자는 core/engine 이 센다.
[켜기] · [올리기]는 화면이 보낸 규칙을 믿지 않는다. 서버가 확정 지식 · 저장한 제안 · 저장한 대화에서 같은 규칙을 다시 찾아
검사(valid_spec)한 것만 넣는다. AI 호출(말로 만들기, 새로 추천받기, 이번 주 요약)은 부른 사람의 워크스페이스로 사용 기록을 남긴다."""
import asyncio
import json
import os
import time
from typing import Literal

import httpx

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

PERIOD = Query('이번 주', pattern='^(오늘|이번 주|이번 달|올해)$')
KIND = Query(..., pattern='^(지표|업무)$')
TABLE = {'지표': 'widgets', '업무': 'automations'}


class Cond(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    prop: str = Field(min_length=1, max_length=200)
    op: str = Field(min_length=1, max_length=40)
    value: str | None = Field(default=None, max_length=200)


class PickSpec(BaseModel):
    """[골라서 만들기]에서 고른 것: 기록 종류 · 셀 방법 · 칸 · 나눌 칸 · 모양 · 고를 기록."""
    model_config = ConfigDict(extra='forbid', strict=True)
    type: str = Field(min_length=1, max_length=200)
    shape: Literal['숫자 하나', '막대', '선', '표', '상태별', '달력', '목록']
    fn: Literal['count', 'sum', 'avg', 'max', 'min'] = 'count'
    prop: str | None = Field(default=None, max_length=200)
    by: str | None = Field(default=None, max_length=200)
    conditions: list[Cond] = Field(default_factory=list, max_length=5)


class Adopt(BaseModel):
    """[켜기] · [올리기]. source 가 규칙을 어디서 다시 찾을지 정한다."""
    model_config = ConfigDict(extra='forbid', strict=True)
    title: str = Field(min_length=1, max_length=200)
    source: Literal['rule', 'proposal', 'gallery', 'pick', 'chat'] = 'rule'
    chat_id: int | None = Field(default=None, ge=1)
    index: int | None = Field(default=None, ge=0, le=500)
    pick: PickSpec | None = None


class Preview(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    pick: PickSpec


class AutomationStatus(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    status: Literal['켜짐', '꺼짐']


class WidgetStatus(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    status: Literal['올림', '내림']


class Settle(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    ok: bool


class Talk(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['지표', '업무']
    request: str = Field(min_length=1, max_length=500)
    chat_id: int | None = Field(default=None, ge=1)


class ChatAction(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    action: Literal['rename', 'drop', 'restore']
    title: str | None = Field(default=None, max_length=100)


class State(dict):
    """한 요청이 읽은 것. 확정 지식 K 는 처음 S['K'] 를 볼 때 묶는다. 앞에서 센 결과를 다시 쓰는 요청(backend.ask.remembered)은 묶지 않고 끝난다."""
    def __missing__(self, key):
        if key != 'K':
            raise KeyError(key)
        from core import engine
        self['K'] = engine.load(self['t'])
        return self['K']


def snapshot(g, token, tid):
    """확정 지식 K, 자동화 · 지표 줄, 기다리는 지표 · 업무 제안. 한 번 읽어 여러 카드를 센다."""
    from backend.ask import open_reader
    t, http = open_reader(g, token, tid)
    try:
        S = State({'t': t,
                   'autos': t.get('automations', select='id,spec,status', order='id'),
                   'widgets': t.get('widgets', select='id,spec,status', order='id'),
                   'proposals': t.get('proposals', select='id,kind,payload', status='eq.대기', kind='in.(지표,업무)', order='id')})
        return S, http
    except BaseException:
        http.close()
        raise


def read_failed(exc):
    print(json.dumps({'insights': 'failed', 'error_type': type(exc).__name__,
                      'read': str(exc) if str(exc).startswith('read_failed:') else None}), flush=True)
    return HTTPException(503, '기록을 읽지 못했어요. 잠시 뒤 다시 눌러 주세요.')


async def can_review(g, token, tid):
    return bool(await g.rpc(token, 'passo_access', {'tid': tid, 'operation': 'review'}))


async def log_usage(g, token, tid, calls, started, tag):
    """AI 호출마다 ai_logs 한 줄. 남기지 못해도 이미 받은 답은 돌려준다."""
    from core import llm
    for u in calls:
        price = llm.PRICE[u['model']]
        cost = (u['input_tokens'] * price[0] + u['output_tokens'] * price[1]) / 1_000_000
        try:
            await g.rpc(token, 'passo_log_ai', {'tid': tid, 'model': u['model'], 'prompt': u['prompt'], 'answer': u['answer'],
                'input_tokens': u['input_tokens'], 'output_tokens': u['output_tokens'], 'cost_usd': round(cost, 6),
                'duration_ms': round((time.monotonic() - started) * 1000)})
        except (HTTPException, ValueError):
            print(json.dumps({tag: 'usage_log_failed'}), flush=True)


def ai_kit(calls):
    """API 서버의 AI 연결(RUNYOUR_API_KEY 우선)과, 호출을 calls 에 모으는 사용 기록 창구."""
    import anthropic
    from core import llm
    sink = lambda t, m, prompt, answer, used_in, used_out, started=None: calls.append(
        {'model': m, 'prompt': prompt, 'answer': answer, 'input_tokens': used_in, 'output_tokens': used_out})
    return anthropic.Anthropic(**llm.connect(os.environ)), sink


def pick_spec(K, p):
    """[골라서 만들기]에서 고른 것 → 지표 명세. 제목은 코드가 고른 것으로 짓는다."""
    from core import engine
    conds = [{'prop': c.prop, 'op': c.op, 'value': c.value, 'value_prop': None} for c in p.conditions]
    if p.shape == '숫자 하나':
        s = {'kind': 'kpi', 'type': p.type, 'fn': p.fn, 'prop': None if p.fn == 'count' else p.prop, 'props': [], 'conditions': conds}
    elif p.shape in ('달력', '목록'):  # 일정 보기는 나눌 날짜 칸이 일정이 적힌 칸이다
        s = {'kind': 'pick', 'type': p.type, 'shape': p.shape, 'fn': 'count', 'prop': p.by, 'by': None, 'color': None, 'conditions': conds}
    else:
        s = {'kind': 'pick', 'type': p.type, 'shape': p.shape, 'fn': p.fn, 'prop': None if p.fn == 'count' else p.prop,
             'by': p.by, 'color': None, 'conditions': conds}
    s['title'] = engine.pick_title(s)
    return s


def pick_options(K):
    """[골라서 만들기]의 고를 거리: 기록 종류마다 숫자 칸 · 나눌 칸 · 날짜 칸, 고를 기록에 쓸 값."""
    from core import engine
    out = []
    for T in K['types']:
        df, groups = engine.frame(K, T), engine.group_cols(K, T)
        values = {n: [str(v) for v in df[n].dropna().astype(str).value_counts().index[:engine.GROUP_MAX]] for n in groups if n in df}
        out.append({'type': T, 'numbers': engine.prop_names(K, T, 'number'), 'groups': groups, 'dates': engine.date_cols(K, T),
                    'values': values})
    return out


def render_chat(K, kind, c, period):
    """대화 한 개를 화면에 보일 모양으로: 말마다 글, 초안의 미리보기(지표는 보기, 업무는 지금 걸린 것), 반영했는지."""
    from core import engine, insights as ins
    msgs = []
    for i, m in enumerate(c['messages']):
        out = {'index': i, 'role': m['role'], 'text': m.get('text', ''), 'done': bool(m.get('done'))}
        s = m.get('spec')
        if s and m['role'] == 'assistant':
            if engine.valid_spec(K, s):
                out['preview'] = ins.view(K, s, period) if kind == '지표' else ins.suggestion_card(K, s)
            else:
                out['stale'] = '확정한 칸이 바뀌어 이 초안은 더 그릴 수 없어요.'
            out['title'] = s.get('title')
        msgs.append(out)
    last = next((m for m in reversed(c['messages']) if m.get('spec') and m['role'] == 'assistant'), None)
    chips = []
    if kind == '지표' and last and not last.get('done'):
        T = last['spec'].get('type')
        ent = engine.entity(K, T) if T in K['types'] else None
        chips = ([f'{ent}별로 나눠줘'] if ent else []) + ['지난달만', '표로 보여줘']
    return {'id': c['id'], 'title': engine.chat_title(c), 'messages': msgs, 'chips': chips}


def chat_row(c):
    from core import engine
    return {'id': c['id'], 'title': engine.chat_title(c), 'made': engine.chat_made(c), 'updated_at': c['updated_at'],
            'deleted_at': c['deleted_at'], 'days_left': engine.days_left(c) if c['deleted_at'] else None}


def install_routes(app, session, gateway):
    from backend.ask import remembered

    async def run(g, token, tid, work):
        def job():
            S, http = snapshot(g, token, tid)
            try:
                return work(S)
            finally:
                http.close()
        try:
            return await asyncio.to_thread(job)
        except (RuntimeError, httpx.HTTPError) as exc:  # 기록을 읽지 못했거나 DB 에 닿지 못했다
            raise read_failed(exc) from None

    async def run_ai(g, token, tid, work, tag):
        """AI 를 부르는 일. 실패하면 503, 성공하면 호출마다 사용 기록."""
        import anthropic
        calls, started = [], time.monotonic()

        def with_ai(S):
            client, sink = ai_kit(calls)
            with client:
                return work(S, client, sink)
        try:
            result = await run(g, token, tid, with_ai)
        except anthropic.APIError as exc:
            print(json.dumps({tag: 'failed', 'error_type': type(exc).__name__, 'status': getattr(exc, 'status_code', None)}), flush=True)
            raise HTTPException(503, 'AI가 답하지 못했어요. 잠시 뒤 다시 눌러 주세요.') from None
        await log_usage(g, token, tid, calls, started, tag)
        return result

    async def my_chats(g, token, tid, kind):
        return await g.rpc(token, 'passo_chats', {'tid': tid, 'chat_kind': kind}) or []

    # ---- 홈 ----

    @app.get('/v1/workspaces/{tid}/home')
    async def home(tid: int, period: str = PERIOD, token=Depends(session), g=Depends(gateway)):
        """오늘 먼저 볼 것(걸린 자동화가 많은 순서로 두 장), 더 걸린 것 · 걸린 것이 없는 것, 보는 기간 한눈에."""
        await g.authorize(token, tid)
        from core import insights as ins

        def work(S):
            K, on = S['K'], [a for a in S['autos'] if a['status'] == '켜짐']
            cards = [{'id': a['id'], **ins.automation_card(K, a['spec'], period, detail=False)} for a in on]
            hit = sorted([c for c in cards if c['count']], key=lambda c: -c['count'])
            shown = [{'id': c['id'], **ins.automation_card(K, next(a['spec'] for a in on if a['id'] == c['id']), period)}
                     for c in hit[:ins.HOME_MAX]]
            return {'enabled': len(on), 'alerts': shown,
                    'more': [{'title': c['title'], 'count': c['count']} for c in hit[ins.HOME_MAX:]],
                    'quiet': [c['title'] for c in cards if not c['count']],
                    'glance': ins.glance(K, [w['spec'] for w in S['widgets'] if w['status'] == '올림'], period) if K['types'] else []}
        return await run(g, token, tid, lambda S: remembered(S['t'], 'home', [period, S['autos'], S['widgets']], lambda: work(S)))

    # ---- 자동화 ----

    @app.get('/v1/workspaces/{tid}/automations')
    async def automations(tid: int, period: str = PERIOD, token=Depends(session), g=Depends(gateway)):
        await g.authorize(token, tid)
        from core import engine, insights as ins
        editable = await can_review(g, token, tid)

        def work(S):
            K, autos = S['K'], S['autos']
            taken = {a['spec'].get('title') for a in autos}
            _, rules = ins.suggestions(K, taken)
            asked = [q for q in S['proposals'] if q['kind'] == '업무' and q['payload'].get('title') not in taken
                     and engine.valid_spec(K, q['payload'])]
            return {'has_records': bool(K['types']),
                    'enabled': [{'id': a['id'], **ins.automation_card(K, a['spec'], period)} for a in autos if a['status'] == '켜짐'],
                    'off': [{'id': a['id'], 'title': a['spec'].get('title')} for a in autos if a['status'] == '꺼짐'],
                    'suggestions': [{'source': 'proposal', 'id': q['id'], **ins.suggestion_card(K, q['payload'])} for q in asked] +
                                   [{'source': 'rule', **ins.suggestion_card(K, s)} for s in rules]}
        return await run(g, token, tid, lambda S: {'can_edit': editable,
                                                     **remembered(S['t'], 'automations', [period, S['autos'], S['proposals']], lambda: work(S))})

    async def resolve(g, token, tid, kind, body):
        """[켜기] · [올리기]할 규칙을 서버가 다시 찾는다. (규칙, 넣은 뒤 할 일)."""
        from core import engine, insights as ins
        chat = None
        if body.source == 'chat':
            if body.chat_id is None or body.index is None:
                raise HTTPException(422, '대화를 고르세요.')
            chat = next((c for c in await my_chats(g, token, tid, kind) if c['id'] == body.chat_id and not c['deleted_at']), None)
            if not chat or body.index >= len(chat['messages']):
                raise HTTPException(404, '대화를 찾지 못했어요.')

        def work(S):
            K = S['K']
            if body.source == 'rule':
                widgets, autos = ins.suggestions(K)
                spec = next((s for s in (widgets if kind == '지표' else autos) if s['title'] == body.title), None)
                return spec, None
            if body.source == 'proposal':
                q = next((q for q in S['proposals'] if q['kind'] == kind and q['payload'].get('title') == body.title), None)
                return (q['payload'], q['id']) if q else (None, None)
            if body.source == 'gallery' and kind == '지표':
                return next((s for s in engine.gallery(K)[0] if s['title'] == body.title), None), None
            if body.source == 'pick' and kind == '지표' and body.pick:
                return pick_spec(K, body.pick), None
            if body.source == 'chat':
                m = chat['messages'][body.index]
                spec = m.get('spec') if m['role'] == 'assistant' and not m.get('done') else None
                return (spec if spec and spec.get('title') == body.title else None), None
            return None, None
        def checked(S):
            spec, qid = work(S)
            return spec, qid, bool(spec) and engine.valid_spec(S['K'], spec)
        spec, qid, valid = await run(g, token, tid, checked)
        if not spec:
            raise HTTPException(409, '제안이 바뀌었어요. 화면을 새로 열어 주세요.')
        if not valid:
            raise HTTPException(422, '기록에 없는 칸이 들어 있어 만들 수 없어요.')

        async def after():
            if qid:
                await g.rpc(token, 'passo_rule_settle', {'tid': tid, 'qid': qid, 'ok': True})
            if chat:
                msgs = [dict(m) for m in chat['messages']]
                msgs[body.index]['done'] = True
                await g.rpc(token, 'passo_chat_save', {'tid': tid, 'chat_kind': kind, 'sid': chat['id'], 'msgs': msgs})
        return spec, after

    @app.post('/v1/workspaces/{tid}/automations', status_code=201)
    async def turn_on(tid: int, body: Adopt, token=Depends(session), g=Depends(gateway)):
        """[켜기]: 규칙 제안 · AI 제안 · 말로 만든 규칙 중 서버가 다시 찾은 같은 것만 켠다."""
        await g.authorize(token, tid, 'review')
        spec, after = await resolve(g, token, tid, '업무', body)
        aid = await g.rpc(token, 'passo_automation_add', {'tid': tid, 'rule': spec})
        await after()
        return {'id': aid}

    @app.post('/v1/workspaces/{tid}/rule-proposals/{qid}')
    async def settle(tid: int, qid: int, body: Settle, token=Depends(session), g=Depends(gateway)):
        """AI가 추천한 지표 · 업무 카드의 [나중에]"""
        await g.authorize(token, tid, 'review')
        await g.rpc(token, 'passo_rule_settle', {'tid': tid, 'qid': qid, 'ok': body.ok})
        return {'id': qid, 'ok': body.ok}

    async def recommend(g, token, tid, kind):
        """[새로 추천받기]: AI가 확정 지식으로 제안하고, 서버가 검사한 것만 카드로 올린다."""
        from core import engine, llm

        def work(S, client, sink):
            t, K = S['t'], S['K']
            if not K['types']:
                return []
            taken = {x for x in engine.known_titles(t, kind, TABLE[kind]) if x}
            fn = llm.propose_widgets if kind == '지표' else llm.propose_automations
            out = []
            for s in fn(t, llm.DEFAULT, K['types'], engine.schema_text(K), engine.links_text(K), engine.stats_text(K), sorted(taken),
                        api_client=client, log_sink=sink):
                s['type'] = s.pop('record_type')
                if s['title'] not in taken and engine.valid_spec(K, s):
                    taken.add(s['title'])
                    out.append(s)
            return out
        specs = await run_ai(g, token, tid, work, 'recommend')
        for s in specs:
            await g.rpc(token, 'passo_rule_propose', {'tid': tid, 'rule_kind': kind, 'rule': s})
        return {'added': len(specs)}

    @app.post('/v1/workspaces/{tid}/automations/recommend')
    async def recommend_automations(tid: int, token=Depends(session), g=Depends(gateway)):
        await g.authorize(token, tid, 'review')
        return await recommend(g, token, tid, '업무')

    @app.post('/v1/workspaces/{tid}/widgets/recommend')
    async def recommend_widgets(tid: int, token=Depends(session), g=Depends(gateway)):
        await g.authorize(token, tid, 'review')
        return await recommend(g, token, tid, '지표')

    @app.post('/v1/workspaces/{tid}/automations/{aid}')
    async def automation_status(tid: int, aid: int, body: AutomationStatus, token=Depends(session), g=Depends(gateway)):
        """[끄기] · [다시 켜기]"""
        await g.authorize(token, tid, 'review')
        await g.rpc(token, 'passo_automation_status', {'tid': tid, 'aid': aid, 'next_status': body.status})
        return {'id': aid, 'status': body.status}

    # ---- 대시보드 ----

    @app.get('/v1/workspaces/{tid}/dashboard')
    async def dashboard(tid: int, period: str = PERIOD, token=Depends(session), g=Depends(gateway)):
        """기록 현황(저절로), 올린 지표, 추천 지표(규칙 · AI), 보기 고르기, 골라서 만들기의 고를 거리."""
        await g.authorize(token, tid)
        from core import engine, insights as ins
        editable = await can_review(g, token, tid)

        def work(S):
            K, widgets = S['K'], S['widgets']
            up = [w for w in widgets if w['status'] == '올림']
            taken = {w['spec'].get('title') for w in widgets}
            picks, _ = ins.suggestions(K, taken)
            asked = [q for q in S['proposals'] if q['kind'] == '지표' and q['payload'].get('title') not in taken]
            shown, missing = engine.gallery(K, taken | {q['payload'].get('title') for q in asked}) if K['types'] else ([], [])
            return {'has_records': bool(K['types']), 'period': period,
                    'auto': [ins.view(K, s, period) for s in engine.auto_widgets(K)],
                    'widgets': [{'id': w['id'], **ins.view(K, w['spec'], period)} for w in up],
                    'down': [{'id': w['id'], 'title': w['spec'].get('title')} for w in widgets if w['status'] == '내림'],
                    'suggestions': [{'source': 'proposal', 'id': q['id'], **ins.view(K, q['payload'], period)} for q in asked] +
                                   [{'source': 'rule', **ins.view(K, s, period)} for s in picks],
                    'gallery': [{'source': 'gallery', 'shape': '숫자 하나' if s['kind'] == 'kpi' else s['shape'], 'type': s['type'],
                                 **ins.view(K, s, period)} for s in shown],
                    'gallery_missing': [{'shape': a, 'why': b} for a, b in missing],
                    'pick_options': pick_options(K)}
        return await run(g, token, tid, lambda S: {'can_edit': editable,
                                                     **remembered(S['t'], 'dashboard', [period, S['widgets'], S['proposals']], lambda: work(S))})

    @app.post('/v1/workspaces/{tid}/widgets/preview')
    async def preview(tid: int, body: Preview, period: str = PERIOD, token=Depends(session), g=Depends(gateway)):
        """[골라서 만들기]: 고른 것으로 코드가 그린 미리보기, "이렇게 셌어요", 못 그리는 모양의 까닭."""
        await g.authorize(token, tid)
        from core import engine, insights as ins

        def work(S):
            K, p = S['K'], body.pick
            if p.type not in K['types']:
                raise HTTPException(422, '기록 종류를 고르세요.')
            shapes = [{'shape': a, 'why': b} for a, b in engine.shapes_for(K, p.type, p.fn, p.by)]
            s = pick_spec(K, p)
            why = next((x['why'] for x in shapes if x['shape'] == p.shape and x['why']), None)
            if why or not engine.valid_spec(K, s):
                return {'title': s['title'], 'shapes': shapes, 'view': None,
                        'message': f"{p.shape}은(는) {why} 그릴 수 있어요." if why else '고른 칸으로는 그릴 수 없어요.'}
            what = f"{p.type} 기록을 " + ("세었어요" if s.get('fn', 'count') == 'count' else f"{s['prop']} {engine.FNS[s['fn']]}으로 셌어요")
            how = what + (f" · {p.by}별로 나눴어요" if p.by and p.shape not in ('숫자 하나', '달력', '목록') else '')
            cond = ' 그리고 '.join(f"{c.prop} = {c.value}" for c in p.conditions)
            return {'title': s['title'], 'shapes': shapes, 'view': ins.view(K, s, period), 'how': how + (f" · {cond}만" if cond else '')}
        return await run(g, token, tid, work)

    @app.post('/v1/workspaces/{tid}/widgets', status_code=201)
    async def put_up(tid: int, body: Adopt, token=Depends(session), g=Depends(gateway)):
        """[올리기]: 추천 지표 · 보기 고르기 · 골라서 만들기 · 말로 만든 보기."""
        await g.authorize(token, tid, 'review')
        spec, after = await resolve(g, token, tid, '지표', body)
        wid = await g.rpc(token, 'passo_widget_add', {'tid': tid, 'rule': spec})
        await after()
        return {'id': wid}

    @app.post('/v1/workspaces/{tid}/widgets/{wid}')
    async def widget_status(tid: int, wid: int, body: WidgetStatus, token=Depends(session), g=Depends(gateway)):
        """[내리기] · 다시 [올리기]"""
        await g.authorize(token, tid, 'review')
        await g.rpc(token, 'passo_widget_status', {'tid': tid, 'wid': wid, 'next_status': body.status})
        return {'id': wid, 'status': body.status}

    @app.get('/v1/workspaces/{tid}/widgets/{wid}/calendar')
    async def calendar(tid: int, wid: int, mode: str = Query('month', pattern='^(week|month)$'),
                       offset: int = Query(0, ge=-120, le=120), token=Depends(session), g=Depends(gateway)):
        """올린 일정 달력의 [지난주] · [다음 주] · [지난달] · [다음 달]"""
        await g.authorize(token, tid)
        from core import insights as ins

        def work(S):
            w = next((w for w in S['widgets'] if w['id'] == wid and w['spec'].get('shape') == '달력'), None)
            if not w:
                raise HTTPException(404, '달력을 찾지 못했어요.')
            return {'id': wid, **ins.view(S['K'], w['spec'], cal=(mode, offset))}
        return await run(g, token, tid, work)

    # ---- 말로 만들기 대화 ----

    @app.get('/v1/workspaces/{tid}/chats')
    async def chats(tid: int, kind: str = KIND, token=Depends(session), g=Depends(gateway)):
        """내 대화 목록(지운 것은 30일 동안 [되돌리기])."""
        await g.authorize(token, tid, 'review')
        return [chat_row(c) for c in await my_chats(g, token, tid, kind)]

    @app.get('/v1/workspaces/{tid}/chats/{cid}')
    async def chat(tid: int, cid: int, kind: str = KIND, period: str = PERIOD, token=Depends(session), g=Depends(gateway)):
        await g.authorize(token, tid, 'review')
        c = next((c for c in await my_chats(g, token, tid, kind) if c['id'] == cid), None)
        if not c:
            raise HTTPException(404, '대화를 찾지 못했어요.')
        return await run(g, token, tid, lambda S: render_chat(S['K'], kind, c, period))

    @app.post('/v1/workspaces/{tid}/chats')
    async def talk(tid: int, body: Talk, period: str = PERIOD, token=Depends(session), g=Depends(gateway)):
        """말로 만들기 한 턴: AI가 초안을 짓고, 서비스가 칸을 검사해 미리보기만 보여 준다. [올리기] · [켜기]를 눌러야 반영된다."""
        await g.authorize(token, tid, 'review')
        from core import engine, llm
        msgs = []
        if body.chat_id:
            c = next((c for c in await my_chats(g, token, tid, body.kind) if c['id'] == body.chat_id and not c['deleted_at']), None)
            if not c:
                raise HTTPException(404, '대화를 찾지 못했어요.')
            msgs = list(c['messages'])
        req = body.request.strip()

        def work(S, client, sink):
            if not S['K']['types']:
                raise HTTPException(409, '아직 확정한 기록이 없어요.')
            history = [{'role': m['role'], 'content': m.get('raw') or m['text']} for m in msgs]
            return engine.build_chat(S['t'], llm.DEFAULT, body.kind, history, req, K=S['K'], api_client=client, log_sink=sink)
        out = await run_ai(g, token, tid, work, 'chat')
        msgs += [{'role': 'user', 'text': req}, {'role': 'assistant', 'request': req, **out}]
        sid = await g.rpc(token, 'passo_chat_save', {'tid': tid, 'chat_kind': body.kind, 'sid': body.chat_id, 'msgs': msgs})
        c = {'id': sid, 'title': None, 'messages': msgs}
        return await run(g, token, tid, lambda S: render_chat(S['K'], body.kind, c, period))

    @app.post('/v1/workspaces/{tid}/chats/{cid}')
    async def chat_action(tid: int, cid: int, body: ChatAction, token=Depends(session), g=Depends(gateway)):
        """[이름 바꾸기] · [지우기] · [되돌리기]. 대화를 지워도 올린 지표 · 켜 둔 자동화는 그대로다."""
        await g.authorize(token, tid, 'review')
        await g.rpc(token, 'passo_chat_update', {'tid': tid, 'sid': cid, 'action': body.action, 'new_title': body.title})
        return {'id': cid, 'action': body.action}

    # ---- 이번 주 요약 ----

    @app.post('/v1/workspaces/{tid}/week-summary')
    async def week_summary(tid: int, token=Depends(session), g=Depends(gateway)):
        """[이번 주 요약 만들기]: 숫자는 engine 이 세고, Claude 는 그 숫자로 문장만 쓴다."""
        await g.authorize(token, tid)
        from core import engine, llm, insights as ins

        def work(S, client, sink):
            K = S['K']
            if not K['types']:
                return None
            lines, facts = engine.week_summary(S['t'], llm.DEFAULT, K, api_client=client, log_sink=sink)
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
        result = await run_ai(g, token, tid, work, 'week')
        if result is None:
            raise HTTPException(409, '아직 확정한 기록이 없어요.')
        return result
