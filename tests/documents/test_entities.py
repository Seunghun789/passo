"""대상 등록 계획: 새 종류의 주 대상 칸은 분류가 되고, 띄어쓰기 · 대소문자만 다른 이름은 코드가, 나머지는 AI가 같은 대상을 찾는다."""
from backend.structure import Reader
from core import engine
from core.entities import confirmed_plan, plan


def K_with(entities=(), ref='설비'):
    tables = {
        'object_types': [{'name': '설비 점검', 'kind': '기록', 'parent_name': None, 'trust': None}]
                        + ([{'name': ref, 'kind': '대상', 'parent_name': None, 'trust': None}] if entities else []),
        'property_defs': [{'type_name': '설비 점검', 'name': '설비', 'dtype': 'text', 'unit': None, 'description': None, 'is_entity': True,
                           'ref_class': ref if entities else None, 'position': 0},
                          {'type_name': '설비 점검', 'name': '진동', 'dtype': 'number', 'unit': None, 'description': None, 'is_entity': False,
                           'ref_class': None, 'position': 1}],
        'alias_dict': [{'type_name': '설비 점검', 'alias': a, 'prop_name': a} for a in ('설비', '진동')],
        'entities': [{'id': i + 1, 'class_name': ref, 'name': n, 'attrs': {}} for i, n in enumerate(entities)],
        'entity_aliases': [{'entity_id': i + 1, 'alias': n} for i, n in enumerate(entities)],
        'records': [{'id': 1, 'type_name': '설비 점검', 'occurred_at': '2026-11-16', 'photo_path': None, 'source_input_id': 1, 'status': '확정',
                     'data': {'설비': 'P-03', '진동': 6}}],
    }
    return engine.load(Reader(lambda t, p: tables.get(t, []), 1))


PROPS = [{'name': '설비', 'label': '설비 번호', 'dtype': 'text', 'is_entity': True, 'ref_class': None},
         {'name': '진동', 'label': '진동', 'dtype': 'number', 'is_entity': False, 'ref_class': None}]


def test_new_type_registers_class_and_entities():
    out = plan(K_with(), '설비 점검', PROPS, [{'설비 번호': 'P-03', '진동': 6}, {'설비 번호': 'P-07'}, {'설비 번호': 'p-07'}])
    assert out['classes'] == [{'type': '설비 점검', 'prop': '설비', 'class': '설비', 'reason': 'AI가 이 칸을 기록의 주 대상으로 봤어요.'}]
    assert out['entities'] == [{'class': '설비', 'name': 'P-03'}, {'class': '설비', 'name': 'P-07'}]
    assert out['same'] == [{'class': '설비', 'value': 'p-07', 'same_as': 'P-07', 'reason': '띄어쓰기 · 대소문자만 달라요.'}]


def test_known_class_uses_spelling_then_ai():
    asked = []
    def match(C, values, known):
        asked.append((C, values))
        assert '- P-03' in known
        return [{'value': '3호 프레스', 'same_as': 'P-03', 'reason': '같은 설비'}, {'value': 'P-09', 'same_as': '없는 이름', 'reason': 'x'}]
    out = plan(K_with(['P-03']), '설비 점검', PROPS, [{'설비 번호': v} for v in ('P-03', 'p -03', '3호 프레스', 'P-09')], match)
    assert out['classes'] == [] and asked == [('설비', ['3호 프레스', 'P-09'])]  # 띄어쓰기만 다른 것은 AI에게 묻지 않는다
    assert {(s['value'], s['same_as']) for s in out['same']} == {('p -03', 'P-03'), ('3호 프레스', 'P-03')}
    assert out['entities'] == [{'class': '설비', 'name': 'P-09'}]  # 목록에 없는 이름을 답하면 새 대상


def test_no_ai_when_nothing_registered_and_numbers_skipped():
    out = plan(K_with(), '설비 점검', PROPS, [{'설비 번호': 'P-03', '진동': 6}], match=lambda *a: (_ for _ in ()).throw(AssertionError('no AI')))
    assert all(c['prop'] != '진동' for c in out['classes'])


def test_confirmed_plan_from_records():
    out = confirmed_plan(K_with())
    assert out['classes'][0]['class'] == '설비' and out['entities'] == [{'class': '설비', 'name': 'P-03'}]
    assert confirmed_plan(K_with(['P-03'])) == {'classes': [], 'entities': [], 'same': []}
