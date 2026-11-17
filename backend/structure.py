"""읽은 종이의 기록 종류·칸 구조를 정한다. 판단은 기존 core/engine·core/llm 그대로이고 여기서는 DB에 쓰지 않는다.
결과는 워커가 passo_worker_finish 에 넘기고, DB가 제안 카드로 만들어 정책대로 반영한다."""
import json
import time


class Reader:
    """engine 이 확정 지식을 읽을 때 쓰는 읽기 전용 창구. 한 워크스페이스의 줄만 읽는다."""
    in_memory = True  # engine.load 가 읽은 표를 붙들어 두지 않고, 조직 설명은 읽지 않는다

    def __init__(self, fetch, tid, cache=None):
        self.fetch, self.id, self.waiting = fetch, tid, None
        self.cache = cache  # engine.load 가 읽은 표를 담아 다음 요청과 나누는 자리. None 이면 매번 새로 읽는다

    def get(self, table, **params):
        from core.record_cells import decode_record
        rows = self.fetch(table, {'tenant_id': f'eq.{self.id}', **params})
        return [decode_record(r) for r in rows] if table == 'records' else rows


def plan_ranges(reader, plan, rows):
    """AI가 범위라고 본 칸(split: 아래값 · 위값 이름)의 적힌 값마다 뜻을 작은 모델이 옮기고(llm.read_ranges),
    계산과 검사는 engine.range_of 가 한다. 한 값이라도 검사를 넘지 못하면 그 칸은 나누지 않는다.
    {칸: {low, high, ranges: {적힌 값: [아래값, 위값]}}}"""
    from core import engine, llm
    out = {}
    for p in plan['props']:
        sp, l = p.get('split') or {}, p['label'].strip()
        lo, hi = (sp.get('low') or '').strip(), (sp.get('high') or '').strip()
        vals = list(dict.fromkeys(str(r[l]) for r in rows if engine.filled(r.get(l))))
        if not (lo and hi and lo != hi and vals):
            continue
        try:
            read = {m['written']: engine.range_of(m['written'], m) for m in llm.read_ranges(reader, l, vals)}
        except Exception as exc:  # 범위로 읽지 못하면 한 칸 그대로 둔다
            print(json.dumps({'ranges': 'skipped', 'error_type': type(exc).__name__}), flush=True)
            continue
        if all(read.get(v) for v in vals):
            out[l] = {'low': lo[:100], 'high': hi[:100], 'ranges': {v: [round(x, 6) for x in read[v]] for v in vals}}
    return out


def _num(x):
    x = round(float(x), 6)
    return str(int(x)) if x == int(x) else str(x)


def split_row(row, splits):
    """적힌 그대로의 한 줄(글 값)에서 범위 칸을 두 숫자 칸으로."""
    row = dict(row)
    for l, sp in splits.items():
        if l in row:
            v = row.pop(l)
            if str(v) in sp['ranges']:
                row[sp['low']], row[sp['high']] = (_num(x) for x in sp['ranges'][str(v)])
    return row


def apply_splits(payload, splits):
    """워커의 반영 내용(칸 상태가 붙은 기록 · 원본 자리)에서 범위 칸을 두 숫자 칸으로 나눈다. 같은 결과를 몇 번 불러도 같다.
    나눈 두 칸은 원본 자리를 함께 잇고, 애매하다고 본 칸이었으면 두 칸 모두 애매한 칸으로 남긴다."""
    from core.record_cells import encode_record
    if not splits:
        return payload
    for r in payload['records']:
        for l, sp in splits.items():
            cell = r['data'].get(l)
            if cell is None:
                continue
            written = str(cell.get('raw') if isinstance(cell, dict) else cell)
            if written not in sp['ranges']:
                continue
            lo, hi = sp['ranges'][written]
            del r['data'][l]
            r['data'].update(encode_record({'data': {sp['low']: _num(lo), sp['high']: _num(hi)}})['data'])
            if l in r.get('uncertain', []):
                i = r['uncertain'].index(l)
                r['uncertain'][i:i + 1] = [sp['low'], sp['high']]
    for l, sp in splits.items():
        if l in payload.get('spans', {}):
            for n in (sp['low'], sp['high']):
                payload['spans'][n] = payload['spans'][l]
    return payload


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
        splits = plan_ranges(reader, plan, rows)
    finally:
        llm.client, llm.log = old
    if splits:  # 범위 칸은 아래값 · 위값 두 숫자 칸으로 본다(워커가 apply_splits 로 기록도 같이 나눈다)
        rows = [split_row(r, splits) for r in rows]
        labels = [n for l in labels for n in ((splits[l]['low'], splits[l]['high']) if l in splits else (l,))]
        plan = {**plan, 'props': [q for p in plan['props'] for q in (
            [{**p, 'label': n, 'name': n, 'kind': '숫자', 'is_entity': False, 'ref_class': None, 'similar_to': None, 'split': None}
             for n in (splits[p['label'].strip()]['low'], splits[p['label'].strip()]['high'])] if p['label'].strip() in splits else [p])]}
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
    return {'type': T[:200], 'title': title, 'props': props, 'links': links, 'samples': samples, 'evidence': ai, 'splits': splits,
            'usage': usage, 'seconds': round(time.monotonic() - started, 3)}


def plan_entities(reader, structure, records, client):
    """구조가 정해진 새 기록에서 대상 등록 계획. 같은 대상 비교만 AI(작은 모델)를 부른다."""
    from core import engine
    from core.entities import matcher, plan
    from core.record_cells import decode_record
    K = engine.load(reader)
    rows = [decode_record({'data': r['data']})['data'] for r in records]
    usage, started = [], time.monotonic()
    sink = lambda t, model, prompt, answer, used_in, used_out, started=None: usage.append(
        {'model': model, 'input_tokens': used_in, 'output_tokens': used_out})
    props = [{**p, 'name': p.get('similar_to') or p['name']} for p in structure['props']]
    out = plan(K, structure['type'], props, rows, matcher(reader, client, sink))
    return {**out, 'usage': usage, 'seconds': round(time.monotonic() - started, 3)}
