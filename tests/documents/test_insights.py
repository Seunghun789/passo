"""홈 · 대시보드 · 자동화 API: 숫자는 기록에서 세고, 켜기 · 올리기는 서버가 다시 만든 규칙만 넣는다."""
from datetime import date, timedelta
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend import ask as ask_module
from backend import insights
from backend.structure import Reader
from core.record_cells import encode_record

day = lambda n: (date.today() - timedelta(days=n)).isoformat()
# 생수는 이틀마다 들어오다 열흘째 없고, 라면은 오늘도 들어왔다 → '재고 점검 4일 넘게 없음'에 생수만 걸린다
ROWS = [('생수', n, 40 - n) for n in (10, 12, 14, 16)] + [('라면', n, 12) for n in (0, 2, 4, 6)]


def tables(autos=(), widgets=()):
    return {
        'object_types': [{'name': '재고 점검', 'kind': '기록', 'parent_name': None, 'trust': None}],
        'property_defs': [{'type_name': '재고 점검', 'name': '품목', 'dtype': 'text', 'unit': None, 'description': None, 'is_entity': True, 'ref_class': None, 'position': 0},
                          {'type_name': '재고 점검', 'name': '수량', 'dtype': 'number', 'unit': '개', 'description': None, 'is_entity': False, 'ref_class': None, 'position': 1}],
        'alias_dict': [{'type_name': '재고 점검', 'alias': a, 'prop_name': a} for a in ('품목', '수량')],
        'records': [encode_record({'id': i + 1, 'type_name': '재고 점검', 'occurred_at': day(n), 'photo_path': None, 'source_input_id': 50 + i, 'status': '확정',
                                   'data': {'품목': name, '수량': str(q)}}) for i, (name, n, q) in enumerate(ROWS)],
        'automations': list(autos), 'widgets': list(widgets), 'proposals': [],
    }


class Gateway:
    url, key = 'https://example.invalid', 'sb_publishable_x'

    def __init__(self, ops=('read', 'review')):
        self.ops, self.calls = ops, []

    async def authorize(self, token, tid, operation='read'):
        if operation not in self.ops:
            raise HTTPException(403, 'no')

    async def rpc(self, token, name, body):
        assert token == 'caller'
        if name == 'passo_access':
            return body['operation'] in self.ops
        self.calls.append((name, body))
        return 9


def client(monkeypatch, g, data=None):
    data = data or tables()
    seen = {'closed': 0}
    def open_reader(gateway, token, tid):
        assert (token, tid) == ('caller', 7)
        def fetch(table, params):
            rows = data.get(table, [])
            if params.get('status', '').startswith('eq.'):
                rows = [r for r in rows if r.get('status') == params['status'][3:]]
            return rows
        return Reader(fetch, tid), SimpleNamespace(close=lambda: seen.__setitem__('closed', seen['closed'] + 1))
    monkeypatch.setattr(ask_module, 'open_reader', open_reader)
    app = FastAPI()
    insights.install_routes(app, lambda: 'caller', lambda: g)
    return TestClient(app), seen


GAP = '재고 점검 4일 넘게 없음'


def test_gap_suggestion_counts_hits_and_backtest(monkeypatch):
    c, seen = client(monkeypatch, Gateway())
    out = c.get('/v1/workspaces/7/automations').json()
    assert out['can_edit'] and out['has_records'] and out['enabled'] == []
    s = next(s for s in out['suggestions'] if s['title'] == GAP)
    assert s['count'] == 1 and s['chip'] == '빠진 기록' and s['backtest'] >= 1
    assert [r['values']['품목'] for r in s['evidence']['rows']] == ['생수']
    assert s['evidence']['rows'][0]['source_id'] == 50  # 근거 줄에서 원본 종이를 연다
    assert seen['closed'] == 1


def test_turn_on_uses_server_rule_not_client_rule(monkeypatch):
    g = Gateway()
    c, _ = client(monkeypatch, g)
    assert c.post('/v1/workspaces/7/automations', json={'title': GAP}).status_code == 201
    name, body = g.calls[0]
    assert name == 'passo_automation_add' and body['rule']['title'] == GAP
    assert body['rule']['conditions'][0]['op'] == 'older_than_days'
    assert c.post('/v1/workspaces/7/automations', json={'title': '아무 규칙'}).status_code == 409
    assert c.post('/v1/workspaces/7/automations', json={'title': GAP, 'conditions': []}).status_code == 422
    assert len(g.calls) == 1


def test_viewer_reads_but_cannot_change(monkeypatch):
    g = Gateway(ops=('read',))
    c, _ = client(monkeypatch, g)
    assert c.get('/v1/workspaces/7/automations').json()['can_edit'] is False
    assert c.post('/v1/workspaces/7/automations', json={'title': GAP}).status_code == 403
    assert c.post('/v1/workspaces/7/automations/3', json={'status': '꺼짐'}).status_code == 403
    assert c.post('/v1/workspaces/7/widgets/3', json={'status': '내림'}).status_code == 403
    assert g.calls == []


def test_status_values_are_checked(monkeypatch):
    g = Gateway()
    c, _ = client(monkeypatch, g)
    assert c.post('/v1/workspaces/7/automations/3', json={'status': '삭제'}).status_code == 422
    assert c.post('/v1/workspaces/7/automations/3', json={'status': '꺼짐'}).json() == {'id': 3, 'status': '꺼짐'}
    assert g.calls == [('passo_automation_status', {'tid': 7, 'aid': 3, 'next_status': '꺼짐'})]


def test_home_shows_enabled_hits_and_glance(monkeypatch):
    from core import insights as ins
    _, rules = ins.suggestions(__import__('core.engine', fromlist=['load']).load(Reader(lambda t, p: tables().get(t, []), 7)))
    gap = next(r for r in rules if r['title'] == GAP)
    quiet = {**gap, 'title': '수량 1000 넘음', 'conditions': [{'prop': '수량', 'op': '>', 'value': '1000', 'value_prop': None}]}
    data = tables(autos=[{'id': 1, 'spec': gap, 'status': '켜짐'}, {'id': 2, 'spec': quiet, 'status': '켜짐'},
                         {'id': 3, 'spec': {**gap, 'title': '꺼 둔 것'}, 'status': '꺼짐'}])
    c, _ = client(monkeypatch, Gateway(), data)
    out = c.get('/v1/workspaces/7/home').json()
    assert out['enabled'] == 2 and out['quiet'] == ['수량 1000 넘음'] and out['more'] == []
    a = out['alerts'][0]
    assert a['id'] == 1 and a['count'] == 1 and a['headline'] == '생수 기록이 10일째 없어요'
    assert a['targets'][0]['name'] == '생수' and '기준 4일' in a['targets'][0]['why']
    g = out['glance'][0]
    assert g['title'] == '재고 점검 기록 수' and g['value'] == '4' and g['previous'] == '2' and g['evidence'] == 4  # 이번 주 0·2·4·6일 전, 지난주(7~13일 전) 10·12일 전
    # 켜 둔 자동화 화면에는 같은 제목의 제안이 다시 나오지 않는다
    auto = c.get('/v1/workspaces/7/automations').json()
    assert GAP not in [s['title'] for s in auto['suggestions']] and [o['title'] for o in auto['off']] == ['꺼 둔 것']


def test_dashboard_counts_and_trend(monkeypatch):
    widgets = [{'id': 4, 'status': '올림', 'spec': {'title': '수량 10 미만 건수', 'kind': 'count_where', 'type': '재고 점검',
                                                   'conditions': [{'prop': '수량', 'op': '<', 'value': '30', 'value_prop': None}]}}]
    c, _ = client(monkeypatch, Gateway(), tables(widgets=widgets))
    out = c.get('/v1/workspaces/7/dashboard', params={'period': '이번 달'}).json()
    kinds = {w['title']: w for w in out['auto']}
    assert kinds['재고 점검 기록 수']['kind'] == 'number'
    trend = kinds['재고 점검 · 수량 추이']
    assert trend['kind'] == 'trend' and set(trend['series']['lines']) <= {'생수', '라면', '분류 안 됨'}
    w = out['widgets'][0]
    assert w['id'] == 4 and w['previous_label'] == '지난달' and w['evidence']['total'] == int(w['value'])
    assert c.get('/v1/workspaces/7/dashboard', params={'period': '내일'}).status_code == 422


def test_week_summary_numbers_from_code_and_logged(monkeypatch):
    g = Gateway()
    c, _ = client(monkeypatch, g)
    import json
    import anthropic
    sent = {}

    class Stream:
        def __init__(self, kw): sent.update(kw)
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def get_final_message(self):
            text = json.dumps({'lines': [{'text': '이번 주 재고 점검은 4건이에요.', 'facts': [0]}]}, ensure_ascii=False)
            return SimpleNamespace(stop_reason='end_turn', content=[SimpleNamespace(type='text', text=text)],
                                   usage=SimpleNamespace(input_tokens=300, output_tokens=40))

    class Fake:
        def __init__(self, **kw): self.base_url = kw.get('base_url', '')
        def __enter__(self): return self
        def __exit__(self, *a): pass
        messages = SimpleNamespace(stream=lambda **kw: Stream(kw))
    monkeypatch.setattr(anthropic, 'Anthropic', Fake)
    monkeypatch.setenv('RUNYOUR_API_KEY', 'k')
    r = c.post('/v1/workspaces/7/week-summary')
    assert r.status_code == 200, r.text
    out = r.json()
    assert out['lines'][0]['text'] == '이번 주 재고 점검은 4건이에요.'
    assert out['lines'][0]['evidence']['total'] == 4  # 문장의 근거는 코드가 센 이번 주 기록
    assert out['facts'][0] == {'name': '재고 점검 기록 수', 'now': '4', 'before': '2', 'diff': '2', 'evidence': 4}
    assert '"이번 주": 4' in sent['messages'][-1]['content']
    assert g.calls[0][0] == 'passo_log_ai' and g.calls[0][1]['input_tokens'] == 300
