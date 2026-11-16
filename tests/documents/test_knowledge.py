"""대상 화면 · 지식그래프 API: 대상 표와 그림은 확정 지식에서, 관계는 카드로만, 대상 등록은 DB 함수로."""
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend import ask as ask_module
from backend import knowledge
from backend.structure import Reader
from core.record_cells import encode_record


def tables(registered=True):
    C = [{'name': '품목', 'kind': '대상', 'parent_name': None, 'trust': None}] if registered else []
    return {
        'object_types': [{'name': '재고 점검', 'kind': '기록', 'parent_name': None, 'trust': None}] + C,
        'property_defs': [{'type_name': '재고 점검', 'name': '품목', 'dtype': 'text', 'unit': None, 'description': None, 'is_entity': True,
                           'ref_class': '품목' if registered else None, 'position': 0},
                          {'type_name': '재고 점검', 'name': '수량', 'dtype': 'number', 'unit': '개', 'description': None, 'is_entity': False, 'ref_class': None, 'position': 1},
                          {'type_name': '재고 점검', 'name': '최소', 'dtype': 'number', 'unit': '개', 'description': None, 'is_entity': False, 'ref_class': None, 'position': 2}],
        'alias_dict': [{'type_name': '재고 점검', 'alias': a, 'prop_name': a} for a in ('품목', '수량', '최소')],
        'entities': [{'id': 1, 'class_name': '품목', 'name': '생수', 'attrs': {}}] if registered else [],
        'entity_aliases': [{'entity_id': 1, 'alias': '생수'}, {'entity_id': 1, 'alias': '생수 500'}] if registered else [],
        'link_types': [{'id': 4, 'from_ref': '재고 점검.최소', 'to_ref': '재고 점검.수량', 'kind': '최소 기준', 'reason': None, 'name': None, 'attr_defs': []}],
        'records': [encode_record({'id': i, 'type_name': '재고 점검', 'occurred_at': '2026-11-1' + str(i), 'photo_path': None, 'source_input_id': 1,
                                   'status': '확정', 'data': d}) for i, d in ((1, {'품목': '생수 500', '수량': '3', '최소': '5'}), (2, {'품목': '라면', '수량': '9', '최소': '5'}))],
        'proposals': [{'id': 8, 'kind': '연결', 'status': '대기', 'payload': {'from': '재고 점검.품목', 'to': '재고 점검.수량', 'kind': '연결', 'reason': 'r'}, 'evidence': None}],
        'automations': [], 'widgets': [],
    }


class Gateway:
    url, key = 'https://example.invalid', 'sb_publishable_x'

    def __init__(self, ops=('read', 'review')):
        self.ops, self.calls = ops, []

    async def authorize(self, token, tid, operation='read'):
        if operation not in self.ops:
            raise HTTPException(403, 'no')

    async def rpc(self, token, name, body):
        if name == 'passo_access':
            return body['operation'] in self.ops
        self.calls.append((name, body))
        return {'classes': 1, 'entities': 1, 'same': 0} if name == 'passo_entities_apply' else 12


def client(monkeypatch, g, data):
    def open_reader(gateway, token, tid):
        def fetch(table, params):
            rows = data.get(table, [])
            if params.get('evidence->>user') == 'eq.true':
                rows = [r for r in rows if (r.get('evidence') or {}).get('user') is True]
            for k in ('status', 'kind'):
                if params.get(k, '').startswith('eq.'):
                    rows = [r for r in rows if r.get(k) == params[k][3:]]
                elif params.get(k, '').startswith('in.('):
                    rows = [r for r in rows if r.get(k) in params[k][4:-1].split(',')]
            return rows
        return Reader(fetch, tid), SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(ask_module, 'open_reader', open_reader)
    app = FastAPI()
    knowledge.install_routes(app, lambda: 'caller', lambda: g)
    return TestClient(app)


def test_entity_table_counts_records_through_aliases(monkeypatch):
    out = client(monkeypatch, Gateway(), tables()).get('/v1/workspaces/7/entities').json()
    C = out['classes'][0]
    assert C['name'] == '품목' and C['pointed_by'] == ['재고 점검.품목']
    assert C['rows'] == [{'id': 1, 'name': '생수', 'aliases': ['생수 500'], 'attrs': {}, 'records': 1}]


def test_recommend_registers_from_confirmed_records(monkeypatch):
    g = Gateway()
    c = client(monkeypatch, g, tables(registered=False))
    import anthropic
    class Fake:
        def __init__(self, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
    monkeypatch.setattr(anthropic, 'Anthropic', Fake)
    monkeypatch.setenv('RUNYOUR_API_KEY', 'k')
    assert c.post('/v1/workspaces/7/entities/recommend').json() == {'classes': 1, 'entities': 1, 'same': 0}
    name, body = g.calls[0]
    assert name == 'passo_entities_apply' and body['plan']['classes'][0]['class'] == '품목'
    assert [e['name'] for e in body['plan']['entities']] == ['생수 500', '라면']  # 처음 등록할 때는 AI를 부르지 않는다
    viewer = Gateway(ops=('read',))
    assert client(monkeypatch, viewer, tables()).post('/v1/workspaces/7/entities/recommend').status_code == 403 and viewer.calls == []


def test_graph_shows_solid_links_and_dashed_proposals(monkeypatch):
    out = client(monkeypatch, Gateway(), tables()).get('/v1/workspaces/7/graph').json()
    ids = {n['id'] for n in out['nodes']}
    assert {'T:재고 점검', 'P:재고 점검.수량', 'C:품목'} <= ids and not any(i.startswith('E:') for i in ids)
    solid = [e for e in out['edges'] if e.get('say', '').startswith("'최소(재고 점검)'")]
    assert solid and not solid[0].get('dashes')
    dashed = [e for e in out['edges'] if e.get('dashes') is True]
    assert dashed and dashed[0]['from'] == 'P:재고 점검.품목'
    assert out['pending'][0]['id'] == 8 and out['pending'][0]['counted'].startswith('같이 적힌 기록')
    assert out['links'] == [{'id': 4, 'text': "'최소(재고 점검)'이(가) '수량(재고 점검)'의 최소 기준이에요."}]
    T = next(n for n in out['nodes'] if n['id'] == 'T:재고 점검')
    assert T['info']['stats'][0] == ['기록', '2줄']
    with_e = client(monkeypatch, Gateway(), tables()).get('/v1/workspaces/7/graph', params={'entities': 'true'}).json()
    assert any(n['id'] == 'E:1' for n in with_e['nodes'])


def test_user_link_checks_refs_and_existing(monkeypatch):
    g = Gateway()
    c = client(monkeypatch, g, tables())
    ok = c.post('/v1/workspaces/7/links', json={'from_ref': '재고 점검.품목', 'to_ref': '품목', 'kind': '연결'})
    assert ok.status_code == 201 and g.calls[0][0] == 'passo_link_propose' and g.calls[0][1]['by_user'] is True
    assert c.post('/v1/workspaces/7/links', json={'from_ref': '재고 점검.없음', 'to_ref': '품목', 'kind': '연결'}).status_code == 422
    assert c.post('/v1/workspaces/7/links', json={'from_ref': '재고 점검.최소', 'to_ref': '재고 점검.수량', 'kind': '최소 기준'}).status_code == 409
    assert c.post('/v1/workspaces/7/links', json={'from_ref': 'a', 'to_ref': 'b', 'kind': '친구'}).status_code == 422
    assert c.post('/v1/workspaces/7/links/4/cut').json() == {'id': 4} and g.calls[-1] == ('passo_link_cut', {'tid': 7, 'link_id': 4})


def test_edits_are_checked_and_become_cards(monkeypatch):
    g = Gateway()
    data = tables()
    data['property_defs'].append({'type_name': '품목', 'name': '단가', 'dtype': 'number', 'unit': '원', 'description': None,
                                  'is_entity': False, 'ref_class': None, 'position': 0})
    c = client(monkeypatch, g, data)
    r = c.post('/v1/workspaces/7/edits', json={'kind': '속성 값', 'payload': {'entity_id': 1, 'attr': '없는 정보', 'new': 3}})
    assert r.status_code == 422 and '정보 더하기' in r.json()['detail']
    assert c.post('/v1/workspaces/7/edits', json={'kind': '속성 값', 'payload': {'entity_id': 1, 'attr': '단가', 'new': 500}}).status_code == 201
    name, body = g.calls[-1]
    assert name == 'passo_user_card' and body['payload'] == {'entity_id': 1, 'entity': '생수', 'class': '품목', 'attr': '단가', 'old': None, 'new': 500}
    assert c.post('/v1/workspaces/7/edits', json={'kind': '칸 설정', 'payload': {'type': '재고 점검', 'op': '단위·설명', 'prop': '수량', 'unit': 'EA', 'description': '창고 수량'}}).status_code == 201
    assert g.calls[-1][1]['payload']['old_unit'] == '개'
    assert c.post('/v1/workspaces/7/edits', json={'kind': '칸 설정', 'payload': {'type': '재고 점검', 'op': '칸 더하기', 'name': '수량'}}).status_code == 422
    assert c.post('/v1/workspaces/7/edits', json={'kind': '상위 분류', 'payload': {'class': '품목', 'parent': '품목'}}).status_code == 422
    assert c.post('/v1/workspaces/7/edits', json={'kind': '종류', 'payload': {}}).status_code == 422
    assert c.post('/v1/workspaces/7/edits/31', json={'ok': True}).status_code == 200 and g.calls[-1] == ('passo_user_card_answer', {'tid': 7, 'qid': 31, 'ok': True})
    viewer = Gateway(ops=('read',))
    assert client(monkeypatch, viewer, data).post('/v1/workspaces/7/edits', json={'kind': '대상 속성', 'payload': {'class': '품목', 'attr': 'x'}}).status_code == 403


def test_pending_cards_show_impact(monkeypatch):
    data = tables()
    data['property_defs'].append({'type_name': '품목', 'name': '최소', 'dtype': 'number', 'unit': None, 'description': None,
                                  'is_entity': False, 'ref_class': None, 'position': 0})
    spec = {'title': '최소 미달', 'type': '재고 점검', 'scope': 'all', 'conditions': [{'prop': '수량', 'op': '<', 'value': None, 'value_prop': '품목.최소'}]}
    data['automations'] = [{'id': 1, 'spec': spec, 'status': '켜짐'}]
    data['proposals'].append({'id': 40, 'kind': '속성 값', 'status': '대기', 'evidence': {'user': True},
                              'payload': {'entity_id': 1, 'entity': '생수', 'class': '품목', 'attr': '최소', 'old': None, 'new': 10}})
    out = client(monkeypatch, Gateway(), data).get('/v1/workspaces/7/entities').json()
    assert out['cards'] == [{'id': 40, 'kind': '속성 값', 'text': "'생수'의 최소: 없음 → 10", 'impact': ["자동화 '최소 미달' 0건 → 1건"]}]
