"""구조 정하기: 기존 engine 판단을 그대로 쓰고, DB 에 쓰지 않으며, AI 가 실패해도 읽은 값은 지킨다."""
from backend.extraction import make_payload
from backend.structure import Reader, plan_structure


def sheet(labels=('품 목', '수량(개)', '점검일')):
    cells = lambda vals: [{'label': l, 'source_raw': v, 'value': v, 'page': 1} for l, v in zip(labels, vals)]
    return {'title': '재고 점검표', 'occurred_at': '2026-11-13', 'columns': list(labels),
            'rows': [{'cells': cells(v)} for v in (('생수', '40', '11/13'), ('라면', '12', '11/13'))]}


def tables(**rows):
    seen = []
    def fetch(table, params):
        seen.append((table, params))
        assert params['tenant_id'] == 'eq.7'
        return rows.get(table, [])
    return fetch, seen


def run(fetch, reply, monkeypatch):
    from core import llm
    calls = []
    def propose(t, model, title, columns, known, pending_types, space=''):
        calls.append({'title': title, 'columns': columns, 'known': known, 'pending': pending_types})
        if isinstance(reply, Exception):
            raise reply
        llm.log(t, model, 'p', 'a', 11, 7)
        return reply
    monkeypatch.setattr(llm, 'propose_schema', propose)
    s = sheet()
    return plan_structure(Reader(fetch, 7), 'claude-sonnet-5-5', s['title'], make_payload(s, {'1': []})['records'], object()), calls


def test_new_type_uses_ai_names_and_code_checked_dtypes(monkeypatch):
    reply = {'type_name': '재고 점검', 'links': [{'from': '품목', 'to': '수량', 'kind': '연결', 'reason': 'r'}, {'from': '품목', 'to': '없는 칸', 'kind': '연결', 'reason': 'r'}],
             'props': [{'label': '품 목', 'name': '품목', 'kind': '글', 'unit': None, 'is_entity': True, 'ref_class': '품목', 'similar_to': None},
                       {'label': '수량(개)', 'name': '수량', 'kind': '날짜', 'unit': '개', 'is_entity': True, 'ref_class': '품목', 'similar_to': None},
                       {'label': '점검일', 'name': '점검일', 'kind': '날짜', 'unit': None, 'is_entity': False, 'ref_class': None, 'similar_to': None}]}
    fetch, seen = tables()
    out, calls = run(fetch, reply, monkeypatch)
    by = {p['label']: p for p in out['props']}
    assert out['type'] == '재고 점검' and out['title'] == '재고 점검표' and out['evidence'] == {}
    assert by['수량(개)']['dtype'] == 'number' and by['수량(개)']['unit'] == '개'  # AI 가 날짜라 해도 적힌 값이 숫자면 숫자
    assert by['점검일']['dtype'] == 'date' and by['품 목']['ref_class'] == '품목' and by['수량(개)']['ref_class'] is None
    assert [p['is_entity'] for p in out['props']] == [True, False, False]  # 대상 칸은 하나만
    assert out['links'] == [{'from': '품목', 'to': '수량', 'kind': '연결', 'reason': 'r'}]
    assert out['samples']['수량(개)'] == ['40', '12'] and out['usage'][0]['input_tokens'] == 11
    assert '수량(개)' in calls[0]['columns'] and {t for t, _ in seen} >= {'object_types', 'property_defs', 'alias_dict', 'proposals'}


def test_known_form_skips_ai_and_same_column_is_marked(monkeypatch):
    known = dict(object_types=[{'name': '재고 점검', 'kind': '기록', 'parent_name': None, 'trust': None}],
                 property_defs=[{'type_name': '재고 점검', 'name': n, 'dtype': 'text', 'unit': None, 'description': None, 'is_entity': False, 'ref_class': None, 'position': i}
                                for i, n in enumerate(('품목', '수량', '점검일'))],
                 alias_dict=[{'type_name': '재고 점검', 'alias': a, 'prop_name': p} for a, p in (('품 목', '품목'), ('수량(개)', '수량'), ('점검일', '점검일'))])
    out, calls = run(tables(**known)[0], RuntimeError('must not be called'), monkeypatch)
    assert out['type'] == '재고 점검' and calls == [] and out['evidence'] == {}
    known['alias_dict'] = known['alias_dict'][:1]
    reply = {'type_name': '재고 점검', 'links': [], 'props': [
        {'label': '수량(개)', 'name': '개수', 'kind': '숫자', 'unit': '개', 'is_entity': False, 'ref_class': None, 'similar_to': '수량'},
        {'label': '점검일', 'name': '점검일', 'kind': '날짜', 'unit': None, 'is_entity': False, 'ref_class': None, 'similar_to': '없는 칸'}]}
    out, calls = run(tables(**known)[0], reply, monkeypatch)
    by = {p['label']: p for p in out['props']}
    assert len(calls) == 1 and '재고 점검' in calls[0]['known']
    assert by['수량(개)']['similar_to'] == '수량' and by['점검일']['similar_to'] == '점검일'  # 이름이 같은 기존 칸


def test_ai_failure_keeps_read_names_and_marks_no_ai(monkeypatch):
    out, _ = run(tables()[0], RuntimeError('provider down'), monkeypatch)
    assert out['type'] == '재고 점검표' and out['evidence'] == {'no_ai': True}
    assert [p['name'] for p in out['props']] == ['품 목', '수량(개)', '점검일']


def test_type_name_never_collides_with_entity_class(monkeypatch):
    fetch, _ = tables(object_types=[{'name': '품목', 'kind': '대상', 'parent_name': None, 'trust': None}])
    out, _ = run(fetch, {'type_name': '품목', 'props': [], 'links': []}, monkeypatch)
    assert out['type'] == '품목 기록'


def test_range_columns_split_into_low_and_high(monkeypatch):
    from backend import structure
    from core import llm
    from core.record_cells import decode_record, encode_record
    reads = {'26~32': {'low': 26, 'high': 32}, '5,210 ±10%': {'base': 5210, 'pct': 10}}
    monkeypatch.setattr(llm, 'read_ranges', lambda t, label, values: [{'written': v, **reads[v]} for v in values])
    plan = {'props': [{'label': '온도 범위', 'split': {'low': '온도 아래', 'high': '온도 위'}}, {'label': '무게', 'split': {'low': '무게 아래', 'high': '무게 위'}}]}
    rows = [{'온도 범위': '26~32', '무게': '5,210 ±10%'}]
    splits = structure.plan_ranges(None, plan, rows)
    assert splits['온도 범위'] == {'low': '온도 아래', 'high': '온도 위', 'ranges': {'26~32': [26, 32]}}
    assert splits['무게']['ranges']['5,210 ±10%'] == [4689.0, 5731.0]
    payload = {'records': [{'data': encode_record({'data': {'온도 범위': '26~32', '설비': 'P-03', '무게': '-'}})['data'], 'uncertain': ['온도 범위']}],
               'spans': {'온도 범위': [{'rec': 0}]}}
    structure.apply_splits(payload, splits)
    data = decode_record({'data': payload['records'][0]['data']})['data']
    assert data['온도 아래'] == '26' and data['온도 위'] == '32' and '온도 범위' not in data and data['무게'] == '-'  # 빈 값 · '-'는 나누지 않는다
    assert payload['records'][0]['uncertain'] == ['온도 아래', '온도 위'] and payload['spans']['온도 위'] == [{'rec': 0}]
    structure.apply_splits(payload, splits)  # 두 번 불러도 같다
    assert decode_record({'data': payload['records'][0]['data']})['data']['온도 아래'] == '26'


def test_range_not_split_when_any_value_fails(monkeypatch):
    from backend import structure
    from core import llm
    monkeypatch.setattr(llm, 'read_ranges', lambda t, label, values: [{'written': '26~32', 'low': 26, 'high': 99}, {'written': '약 30'}])
    plan = {'props': [{'label': '온도', 'split': {'low': '아래', 'high': '위'}}]}
    assert structure.plan_ranges(None, plan, [{'온도': '26~32'}, {'온도': '약 30'}]) == {}  # 적히지 않은 숫자(99)와 못 읽은 값
