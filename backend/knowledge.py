"""대상 화면과 지식그래프 API. 확정 지식은 부른 사람의 JWT 로만 읽고(RLS), 점 · 선 · 숫자는 core 가 센다.
대상 등록은 core/entities 가 계획하고 DB(passo_entities_apply)가 반영한다. 관계는 '연결' 제안 카드로 올라가고
[맞아요](확인 화면과 같은 passo_answer_review)를 눌러야 이어진다."""
import json
import time
from typing import Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field


class Edit(BaseModel):
    """직접 고친 것. payload 는 core/edits.card 가 확정 지식으로 검사한다."""
    model_config = ConfigDict(extra='forbid', strict=True)
    kind: Literal['속성 값', '대상', '대상 속성', '같은 대상', '상위 분류', '관계 속성', '칸 설정']
    payload: dict


class Apply(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    ok: bool


class LinkPick(BaseModel):
    """[이어 보기]: 두 칸과 관계."""
    model_config = ConfigDict(extra='forbid', strict=True)
    from_ref: str = Field(min_length=1, max_length=300)
    to_ref: str = Field(min_length=1, max_length=300)
    kind: Literal['연결', '함께 움직임', '최소 기준', '최대 기준', '의존', '영향', '대체']
    name: str | None = Field(default=None, max_length=100)


EDIT_KINDS = ('속성 값', '대상', '대상 속성', '같은 대상', '상위 분류', '관계 속성', '칸 설정')
UNDOABLE = ('속성 값', '같은 대상', '칸 설정')  # 반영 전으로 정확히 돌아가는 것만. 기록 종류 · 칸 · 대상 · 분류 확정은 되돌리지 않는다


def edit_cards(S):
    """"직접 고친 것" 카드: 한 줄과, 적용하면 켜 둔 자동화 · 올린 지표가 어떻게 바뀌는지."""
    from core import engine
    from core.edits import card_text
    return [{'id': q['id'], 'kind': q['kind'], 'text': card_text(q), 'impact': engine.impact(S['t'], S['K'], q)} for q in S['cards']]


def class_links(K):
    """대상 분류 사이의 관계와 대상 쌍(관계 정보를 넣을 곳)."""
    from core import engine
    from core.ask import plain
    out = []
    for l in K['links']:
        if '.' in l['from_ref'] or '.' in l['to_ref']:
            continue
        pairs = engine.link_pairs(K, l)
        attrs = [d['name'] for d in l.get('attr_defs') or []]
        out.append({'id': l['id'], 'from': l['from_ref'], 'to': l['to_ref'], 'name': l.get('name') or l['kind'], 'attrs': attrs,
                    'pairs': plain([{'from': str(r[l['from_ref']]), 'to': str(r[l['to_ref']]), 'values': {a: r[a] for a in attrs}}
                                    for r in pairs.head(100).to_dict('records')])})
    return out


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
    from backend.ask import remembered
    import asyncio
    import httpx

    async def run(g, token, tid, work):
        def job():
            S, http = snapshot(g, token, tid)
            try:
                from core import db
                t = S['t']
                pending, cards, done = db.together([  # 서로 기다릴 필요 없는 읽기는 함께 보낸다
                    lambda: t.get('proposals', select='id,kind,payload,evidence', status='eq.대기', kind='eq.연결', order='id'),
                    lambda: t.get('proposals', select='id,kind,payload,evidence', status='eq.대기', order='id', **{'evidence->>user': 'eq.true'}),
                    lambda: t.get('proposals', select='id,kind,payload,evidence,decided_at', status='eq.승인',
                                  order='decided_at.desc', limit=40, **{'evidence->>user': 'eq.true'})])
                S['links_pending'] = pending
                S['cards'] = [q for q in cards if q['kind'] in EDIT_KINDS]
                S['done_cards'] = [q for q in done if q['kind'] in UNDOABLE and not q['payload'].get('undone')
                                   and q['payload'].get('op') != '칸 더하기'][:10]
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
        _, editable = await asyncio.gather(g.authorize(token, tid), can_review(g, token, tid))  # 권한 두 가지를 함께 본다
        from core import engine
        from core.edits import card_text
        return await run(g, token, tid, lambda S: {'can_edit': editable,
                                                     **remembered(S['t'], 'entities', [], lambda: {'has_records': bool(S['K']['types']),
                                                                                                   'classes': entity_table(S['K']), 'links': class_links(S['K'])}),
                                                     'cards': edit_cards(S), 'dtypes': list(engine.DTYPE_KO.items()),
                                                     'undoable': [{'id': q['id'], 'kind': q['kind'], 'text': card_text(q), 'at': q['decided_at']}
                                                                  for q in S['done_cards']]})

    @app.post('/v1/workspaces/{tid}/edits', status_code=201)
    async def edit(tid: int, body: Edit, token=Depends(session), g=Depends(gateway)):
        """[바꾼 것 올리기] · [정보 더하기] · [별칭 더하기] · [하위 분류로 묶기] · [상위 분류 정하기] · [관계 정보 올리기]
        · [단위·설명 올리기] · [다른 이름 더하기] · [칸 더하기]: 바로 쓰지 않고 "직접 고친 것" 카드로 올린다."""
        await g.authorize(token, tid, 'review')
        from core.edits import card

        def work(S):
            try:
                return card(S['K'], body.kind, body.payload)
            except (ValueError, TypeError) as exc:
                raise HTTPException(422, str(exc) if isinstance(exc, ValueError) else '고친 값을 확인해 주세요.') from None
        payload = await run(g, token, tid, work)
        return {'id': await g.rpc(token, 'passo_user_card', {'tid': tid, 'card_kind': body.kind, 'payload': payload})}

    @app.post('/v1/workspaces/{tid}/edits/{qid}/undo')
    async def undo_edit(tid: int, qid: int, token=Depends(session), g=Depends(gateway)):
        """[되돌리기]: 대상 정보 값 · 별칭 · 칸의 단위·설명 · 다른 이름을 고치기 전으로."""
        await g.authorize(token, tid, 'review')
        await g.rpc(token, 'passo_user_card_undo', {'tid': tid, 'qid': qid})
        return {'id': qid}

    @app.post('/v1/workspaces/{tid}/edits/{qid}')
    async def apply_edit(tid: int, qid: int, body: Apply, token=Depends(session), g=Depends(gateway)):
        """카드의 [적용] · [아니요]"""
        await g.authorize(token, tid, 'review')
        return await g.rpc(token, 'passo_user_card_answer', {'tid': tid, 'qid': qid, 'ok': body.ok})

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
        _, editable = await asyncio.gather(g.authorize(token, tid), can_review(g, token, tid))  # 권한 두 가지를 함께 본다
        from core import engine, llm
        from core.graph import graph_data, link_sentence, stated

        def work(S):
            K, pend = S['K'], S['links_pending']
            nodes, edges = graph_data(K, pend, entities)
            return {'has_records': bool(K['types']), 'nodes': nodes, 'edges': edges,
                    'props': {T: [{'name': p['name'], 'dtype': p['dtype'], 'unit': p.get('unit'), 'description': p.get('description')}
                                  for p in K['props'][T]] for T in K['types']},
                    'members': {C: [e['name'] for e in engine.members(K, C)] for C in K['classes']},
                    'class_attrs': {C: [a['name'] for a in engine.class_attrs(K, C)] for C in K['classes']},
                    'links': [{'id': l['id'], 'text': stated(link_sentence({'from': l['from_ref'], 'to': l['to_ref'], 'kind': l['kind'],
                                                                            'name': l.get('name')}))} for l in K['links']],
                    'pending': [{'id': q['id'], 'payload': q['payload'], 'text': link_sentence(q['payload']),
                                 'reason': q['payload'].get('reason'), 'counted': (q.get('evidence') or {}).get('counted') or engine.pair_evidence(K, q['payload']['from'], q['payload']['to'])}
                                for q in pend],
                    'refs': engine.refs(K), 'kinds': llm.LINK_KINDS}
        return await run(g, token, tid, lambda S: {'can_edit': editable, 'cards': edit_cards(S),
                                                     **remembered(S['t'], 'graph', [entities, S['links_pending']], lambda: work(S))})

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
