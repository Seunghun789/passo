"""읽은 종이의 기록 종류·칸 구조를 정한다. 판단은 기존 core/engine·core/llm 그대로이고 여기서는 DB에 쓰지 않는다.
결과는 워커가 passo_worker_finish 에 넘기고, DB가 제안 카드로 만들어 정책대로 반영한다."""
import time


class Reader:
    """engine 이 확정 지식을 읽을 때 쓰는 읽기 전용 창구. 한 워크스페이스의 줄만 읽는다."""
    in_memory = True  # engine.load 가 읽은 표를 붙들어 두지 않고, 조직 설명은 읽지 않는다

    def __init__(self, fetch, tid):
        self.fetch, self.id, self.waiting = fetch, tid, None

    def get(self, table, **params):
        from core.record_cells import decode_record
        rows = self.fetch(table, {'tenant_id': f'eq.{self.id}', **params})
        return [decode_record(r) for r in rows] if table == 'records' else rows


def plan_structure(reader, model, title, records, client):
    """records: make_payload 가 만든 기록(칸 상태가 붙은 data). 기록 종류 이름과 칸 정의, 근거를 돌려준다."""
    from core import engine, llm
    from core.record_cells import decode_record
    rows = [{k: v for k, v in decode_record({'data': r['data']})['data'].items() if engine.filled(v)} for r in records]
    labels = list(dict.fromkeys(l for r in records for l in r['data']))
    K = engine.load(reader)
    usage, started = [], time.monotonic()
    old = llm.client, llm.log
    llm.client = lambda: client
    llm.log = lambda t, model, prompt, answer, usage_in, usage_out, started=None: usage.append(
        {'model': model, 'input_tokens': usage_in, 'output_tokens': usage_out})
    try:
        plan, ai = engine.schema_plan(reader, model, K, title, rows, labels)
    finally:
        llm.client, llm.log = old
    kinds = {p['label'].strip(): p.get('kind') for p in plan['props']}
    values = {l: [r.get(l) for r in rows] for l in labels}
    dtypes = {l: engine.fit_dtype(kinds.get(l), values[l]) or engine.infer_dtype(values[l]) for l in labels}
    T = (plan['type_name'] or '').strip() or title
    if T in K['classes']:
        T = f'{T} 기록'
    existing = {p['name'] for p in K['props'].get(T, [])} if T in K['types'] else set()
    given = {p['label'].strip(): p for p in plan['props']}
    props, names, has_entity = [], set(), False
    for l in labels:
        g = given.get(l, {})
        name = (g.get('name') or l).strip()
        name = l if name in names else name
        names.add(name)
        is_entity = bool(g.get('is_entity')) and not has_entity
        has_entity |= is_entity
        ref = (g.get('ref_class') or '').strip() or None
        same = g.get('similar_to') if g.get('similar_to') in existing else name if name in existing else None
        props.append({'label': l, 'name': name, 'dtype': dtypes[l], 'unit': g.get('unit') or None, 'is_entity': is_entity,
                      'ref_class': ref if dtypes[l] in ('text', 'choice') else None, 'similar_to': same})
    links = [{'from': l['from'], 'to': l['to'], 'kind': l['kind'], 'reason': l.get('reason')} for l in plan['links']
             if l['from'] in names and l['to'] in names and l['from'] != l['to']]
    samples = {l: list(dict.fromkeys(str(v) for v in values[l] if v is not None))[:4] for l in labels}
    return {'type': T[:200], 'title': title, 'props': props, 'links': links, 'samples': samples, 'evidence': ai,
            'usage': usage, 'seconds': round(time.monotonic() - started, 3)}
