"""대상 화면과 지식그래프 API. 확정 지식은 부른 사람의 JWT 로만 읽고(RLS), 점 · 선 · 숫자는 core 가 센다.
대상 등록은 core/entities 가 계획하고 DB(passo_entities_apply)가 반영한다. 관계는 '연결' 제안 카드로 올라가고
[맞아요](확인 화면과 같은 passo_answer_review)를 눌러야 이어진다."""
import json
import time
from typing import Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field


class LinkPick(BaseModel):
    """[이어 보기]: 두 칸과 관계."""
    model_config = ConfigDict(extra='forbid', strict=True)
    from_ref: str = Field(min_length=1, max_length=300)
    to_ref: str = Field(min_length=1, max_length=300)
    kind: Literal['연결', '함께 움직임', '최소 기준', '최대 기준', '의존', '영향', '대체']
    name: str | None = Field(default=None, max_length=100)


def entity_table(K):
    """분류마다 대상 표: 이름 · 별칭 · 정보 · 그 대상을 가리킨 기록 수. 대상을 가리키는 칸도 함께."""
    from core import engine
    used = {}
    for T in K['types']:
        df = engine.frame(K, T)
        for p in engine.ref_props(K, T):
            if p['name'] in df:
                for name, n in df[p['name']].dropna().astype(str).value_counts().items():
                    used[(p['ref_class'], name)] = used.get((p['ref_class'], name), 0) + int(n)
    out = []
    for C, parent in K['classes'].items():
        attrs = [a['name'] for a in engine.class_attrs(K, C)]
        rows = [{'id': e['id'], 'name': e['name'], 'aliases': [a for a in engine.aliases_of(K, e['id']) if a != e['name']],
                 'attrs': {a: e['attrs'].get(a) for a in attrs}, 'records': used.get((C, e['name']), 0)}
                for e in sorted(engine.members(K, C), key=lambda e: e['name'])]
        out.append({'name': C, 'parent': parent, 'attrs': attrs, 'total': len(rows), 'rows': rows,
                    'children': [c for c, p in K['classes'].items() if p == C],
                    'pointed_by': [f"{T}.{p['name']}" for T in K['types'] for p in engine.ref_props(K, T) if p['ref_class'] == C]})
    return out


def install_routes(app, session, gateway):
    from backend.insights import can_review, log_usage, ai_kit, snapshot, read_failed
    import asyncio
    import httpx

    async def run(g, token, tid, work):
        def job():
            S, http = snapshot(g, token, tid)
            try:
                S['links_pending'] = S['t'].get('proposals', select='id,kind,payload,evidence', status='eq.대기', kind='eq.연결', order='id')
                return work(S)
            finally:
                http.close()
        try:
            return await asyncio.to_thread(job)
        except (RuntimeError, httpx.HTTPError) as exc:
            raise read_failed(exc) from None

    async def run_ai(g, token, tid, work, tag):
        import anthropic
        calls, started = [], time.monotonic()

        def with_ai(S):
            client, sink = ai_kit(calls)
            with client:
                return work(S, client, sink)
        try:
            out = await run(g, token, tid, with_ai)
        except anthropic.APIError as exc:
            print(json.dumps({tag: 'failed', 'error_type': type(exc).__name__, 'status': getattr(exc, 'status_code', None)}), flush=True)
            raise HTTPException(503, 'AI가 답하지 못했어요. 잠시 뒤 다시 눌러 주세요.') from None
        await log_usage(g, token, tid, calls, started, tag)
        return out

    # ---- 대상 ----

    @app.get('/v1/workspaces/{tid}/entities')
    async def entities(tid: int, token=Depends(session), g=Depends(gateway)):
        """분류 탭마다 대상 표. 대상을 가리키는 칸이 든 종이를 올리면 저절로 채워진다."""
        await g.authorize(token, tid)
        editable = await can_review(g, token, tid)
        return await run(g, token, tid, lambda S: {'can_edit': editable, 'has_records': bool(S['K']['types']),
                                                     'classes': entity_table(S['K'])})

    @app.post('/v1/workspaces/{tid}/entities/recommend')
    async def recommend_entities(tid: int, token=Depends(session), g=Depends(gateway)):
        """[새로 추천받기]: 확정한 기록 전체에서 대상을 가리키는 칸 · 처음 보는 대상 · 다르게 적힌 같은 대상을 찾아 반영한다."""
        await g.authorize(token, tid, 'review')
        from core.entities import confirmed_plan, matcher

        def work(S, client, sink):
            return confirmed_plan(S['K'], matcher(S['t'], client, sink))
        plan = await run_ai(g, token, tid, work, 'entities')
        if not any(plan.values()):
            return {'classes': 0, 'entities': 0, 'same': 0}
        return await g.rpc(token, 'passo_entities_apply', {'tid': tid, 'plan': plan})

    # ---- 지식그래프 ----

    @app.get('/v1/workspaces/{tid}/graph')
    async def graph(tid: int, entities: bool = Query(False), token=Depends(session), g=Depends(gateway)):
        """점 · 선(확정 실선, 확인할 관계 점선), 확정한 관계 목록, 관계 제안 카드, [이어 보기]에 고를 칸."""
        await g.authorize(token, tid)
        from core import engine, llm
        from core.graph import graph_data, link_sentence, stated
        editable = await can_review(g, token, tid)

        def work(S):
            K, pend = S['K'], S['links_pending']
            nodes, edges = graph_data(K, pend, entities)
            return {'can_edit': editable, 'has_records': bool(K['types']), 'nodes': nodes, 'edges': edges,
                    'links': [{'id': l['id'], 'text': stated(link_sentence({'from': l['from_ref'], 'to': l['to_ref'], 'kind': l['kind'],
                                                                            'name': l.get('name')}))} for l in K['links']],
                    'pending': [{'id': q['id'], 'payload': q['payload'], 'text': link_sentence(q['payload']),
                                 'reason': q['payload'].get('reason'), 'counted': (q.get('evidence') or {}).get('counted') or engine.pair_evidence(K, q['payload']['from'], q['payload']['to'])}
                                for q in pend],
                    'refs': engine.refs(K), 'kinds': llm.LINK_KINDS}
        return await run(g, token, tid, work)

    async def propose(g, token, tid, K, a, b, kind, name, reason, user):
        from core import engine, llm
        if kind not in llm.LINK_KINDS or a == b or a not in engine.refs(K) or b not in engine.refs(K):
            return None
        if any(l['from_ref'] == a and l['to_ref'] == b and l['kind'] == kind for l in K['links']):
            return None
        return await g.rpc(token, 'passo_link_propose', {'tid': tid, 'from_ref': a, 'to_ref': b, 'link_kind': kind, 'link_name': name,
                                                         'reason': reason or '', 'counted': engine.pair_evidence(K, a, b), 'by_user': user})

    @app.post('/v1/workspaces/{tid}/links', status_code=201)
    async def user_link(tid: int, body: LinkPick, token=Depends(session), g=Depends(gateway)):
        """[이어 보기]: 고른 두 칸과 관계를 '관계 제안' 카드로 올린다. 기록으로 센 근거가 붙는다."""
        await g.authorize(token, tid, 'review')
        K = await run(g, token, tid, lambda S: S['K'])
        if any(l['from_ref'] == body.from_ref and l['to_ref'] == body.to_ref and l['kind'] == body.kind for l in K['links']):
            raise HTTPException(409, '이미 확정된 관계예요.')
        qid = await propose(g, token, tid, K, body.from_ref, body.to_ref, body.kind, body.name, '', True)
        if not qid:
            raise HTTPException(422, '고를 수 없는 칸이에요.')
        return {'id': qid}

    @app.post('/v1/workspaces/{tid}/links/recommend')
    async def recommend_links(tid: int, token=Depends(session), g=Depends(gateway)):
        """[새로 추천받기]: AI가 기록으로 센 근거를 보고 관계를 제안한다. 카드로만 올라가고 [맞아요]를 눌러야 이어진다."""
        await g.authorize(token, tid, 'review')
        from core import engine, llm

        def work(S, client, sink):
            K = S['K']
            if not K['types']:
                return K, []
            return K, llm.propose_links(S['t'], llm.DEFAULT, engine.schema_text(K), engine.all_evidence(K), engine.links_text(K),
                                        api_client=client, log_sink=sink)
        K, picks = await run_ai(g, token, tid, work, 'links')
        added = 0
        for l in picks:
            try:
                if await propose(g, token, tid, K, l['from'].strip(), l['to'].strip(), l['kind'], None, l.get('reason'), False):
                    added += 1
            except HTTPException as exc:
                if exc.status_code != 409:
                    raise
        return {'added': added}

    @app.post('/v1/workspaces/{tid}/links/{lid}/cut')
    async def cut(tid: int, lid: int, token=Depends(session), g=Depends(gateway)):
        """[끊기]: 확정한 관계를 지운다. 끊은 기록은 거절한 관계 제안으로 남는다."""
        await g.authorize(token, tid, 'review')
        await g.rpc(token, 'passo_link_cut', {'tid': tid, 'link_id': lid})
        return {'id': lid}
