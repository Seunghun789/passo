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


def tables(autos=(), widgets=(), proposals=()):
    return {
        'object_types': [{'name': '재고 점검', 'kind': '기록', 'parent_name': None, 'trust': None}],
        'property_defs': [{'type_name': '재고 점검', 'name': '품목', 'dtype': 'text', 'unit': None, 'description': None, 'is_entity': True, 'ref_class': None, 'position': 0},
                          {'type_name': '재고 점검', 'name': '수량', 'dtype': 'number', 'unit': '개', 'description': None, 'is_entity': False, 'ref_class': None, 'position': 1}],
        'alias_dict': [{'type_name': '재고 점검', 'alias': a, 'prop_name': a} for a in ('품목', '수량')],
        'records': [encode_record({'id': i + 1, 'type_name': '재고 점검', 'occurred_at': day(n), 'photo_path': None, 'source_input_id': 50 + i, 'status': '확정',
                                   'data': {'품목': name, '수량': str(q)}}) for i, (name, n, q) in enumerate(ROWS)],
        'automations': list(autos), 'widgets': list(widgets), 'proposals': list(proposals),
    }


class Gateway:
    url, key = 'https://example.invalid', 'sb_publishable_x'

    def __init__(self, ops=('read', 'review')):
        self.ops, self.calls = ops, []

    async def authorize(self, token, tid, operation='read'):
        if operation not in self.ops:
            raise HTTPException(403, 'no')

    chats = ()

    async def rpc(self, token, name, body):
        assert token == 'caller'
        if name == 'passo_access':
            return body['operation'] in self.ops
        if name == 'passo_chats':
            return [c for c in self.chats if c['kind'] == body['chat_kind']]
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
    assert trend['kind'] == 'vega' and trend['vega']['config']['range']['category'][0] == '#4F46E5'  # 대화로 만든 보기와 같은 꾸밈
    assert {r['계열'] for r in trend['vega']['data']['values']} <= {'생수', '라면', '분류 안 됨'}
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


QUIET = {'title': '수량 1000 넘음', 'type': '재고 점검', 'scope': 'all',
         'conditions': [{'prop': '수량', 'op': '>', 'value': '1000', 'value_prop': None}]}


def test_ai_proposal_turns_on_and_is_settled(monkeypatch):
    g = Gateway()
    q = {'id': 31, 'kind': '업무', 'payload': QUIET, 'status': '대기'}
    c, _ = client(monkeypatch, g, tables(proposals=[q]))
    out = c.get('/v1/workspaces/7/automations').json()
    s = next(s for s in out['suggestions'] if s['title'] == QUIET['title'])
    assert s['source'] == 'proposal' and s['id'] == 31 and s['count'] == 0
    assert c.post('/v1/workspaces/7/automations', json={'title': QUIET['title'], 'source': 'proposal'}).status_code == 201
    assert [n for n, _ in g.calls] == ['passo_automation_add', 'passo_rule_settle']
    assert g.calls[0][1]['rule'] == QUIET and g.calls[1][1] == {'tid': 7, 'qid': 31, 'ok': True}


def test_chat_rule_must_match_saved_chat(monkeypatch):
    g = Gateway()
    g.chats = [{'id': 5, 'kind': '업무', 'title': None, 'deleted_at': None, 'created_at': '2026-11-17T00:00:00+00:00',
                'updated_at': '2026-11-17T00:00:00+00:00',
                'messages': [{'role': 'user', 'text': '수량 1000 넘으면'}, {'role': 'assistant', 'text': '만들었어요', 'spec': QUIET}]}]
    c, _ = client(monkeypatch, g)
    body = {'title': QUIET['title'], 'source': 'chat', 'chat_id': 5, 'index': 1}
    assert c.post('/v1/workspaces/7/automations', json={**body, 'title': '다른 이름'}).status_code == 409
    assert c.post('/v1/workspaces/7/automations', json={**body, 'index': 0}).status_code == 409
    assert c.post('/v1/workspaces/7/automations', json={**body, 'chat_id': 6}).status_code == 404
    assert c.post('/v1/workspaces/7/automations', json=body).status_code == 201
    assert g.calls[0][0] == 'passo_automation_add' and g.calls[1][0] == 'passo_chat_save'
    assert g.calls[1][1]['msgs'][1]['done'] is True  # 대화에 "켬"이 붙는다
    shown = c.get('/v1/workspaces/7/chats', params={'kind': '업무'}).json()
    assert shown[0]['title'] == QUIET['title'] and shown[0]['made'] is False


def test_pick_preview_and_put_up(monkeypatch):
    g = Gateway()
    c, _ = client(monkeypatch, g)
    pick = {'type': '재고 점검', 'shape': '막대', 'fn': 'avg', 'prop': '수량', 'by': '품목'}
    out = c.post('/v1/workspaces/7/widgets/preview', params={'period': '올해'}, json={'pick': pick}).json()
    assert out['title'] == '품목별 수량 평균' and out['view']['kind'] == 'vega'
    bars = {r['묶음']: r['값'] for r in out['view']['vega']['data']['values']}
    assert bars == {'생수': 27.0, '라면': 12.0} and '수량 평균' in out['how']
    line = c.post('/v1/workspaces/7/widgets/preview', json={'pick': {**pick, 'shape': '선'}}).json()
    assert line['view'] is None and '날짜로 나누면' in line['message']
    assert c.post('/v1/workspaces/7/widgets/preview', json={'pick': {**pick, 'shape': '원'}}).status_code == 422
    assert c.post('/v1/workspaces/7/widgets', json={'title': out['title'], 'source': 'pick', 'pick': pick}).status_code == 201
    assert g.calls[0][0] == 'passo_widget_add' and g.calls[0][1]['rule']['by'] == '품목'
    bad = {**pick, 'by': '없는 칸'}
    assert c.post('/v1/workspaces/7/widgets', json={'title': 'x', 'source': 'pick', 'pick': bad}).status_code == 422


def test_gallery_and_pick_options(monkeypatch):
    c, _ = client(monkeypatch, Gateway())
    out = c.get('/v1/workspaces/7/dashboard').json()
    titles = [v['title'] for v in out['gallery']]
    assert '품목별 건수' in titles and all(v['source'] == 'gallery' for v in out['gallery'])
    opts = out['pick_options'][0]
    assert opts['type'] == '재고 점검' and opts['numbers'] == ['수량'] and '품목' in opts['groups'] and set(opts['values']['품목']) == {'생수', '라면'}


def fake_model(monkeypatch, replies):
    """스트리밍 답을 차례로 돌려주는 가짜 모델. 받은 요청을 sent 에 모은다."""
    import json as _json
    import anthropic
    sent, queue = [], list(replies)

    class Stream:
        def __init__(self, kw): sent.append(kw)
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def get_final_message(self):
            text = _json.dumps(queue.pop(0), ensure_ascii=False)
            return SimpleNamespace(stop_reason='end_turn', content=[SimpleNamespace(type='text', text=text)],
                                   usage=SimpleNamespace(input_tokens=500, output_tokens=60))

    class Fake:
        def __init__(self, **kw): self.base_url = kw.get('base_url', '')
        def __enter__(self): return self
        def __exit__(self, *a): pass
        messages = SimpleNamespace(stream=lambda **kw: Stream(kw))
    monkeypatch.setattr(anthropic, 'Anthropic', Fake)
    monkeypatch.setenv('RUNYOUR_API_KEY', 'k')
    return sent


def test_chat_turn_saves_draft_and_logs(monkeypatch):
    g = Gateway()
    c, _ = client(monkeypatch, g)
    spec = {'title': '수량 5 미만', 'record_type': '재고 점검', 'scope': 'latest', 'reason': '부족',
            'conditions': [{'prop': '수량', 'op': '<', 'value': '20'}]}
    fake_model(monkeypatch, [{'reply': '수량이 20보다 적으면 먼저 볼 것에 올리는 규칙이에요.', 'spec': spec, 'missing': []}])
    r = c.post('/v1/workspaces/7/chats', json={'kind': '업무', 'request': '수량 적으면 알려줘'})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out['id'] == 9 and out['messages'][1]['title'] == '수량 5 미만'
    assert out['messages'][1]['preview']['count'] == 1  # 지금 걸린 것은 코드가 센다(라면 12)
    names = [n for n, _ in g.calls]
    assert names == ['passo_log_ai', 'passo_chat_save']
    saved = g.calls[1][1]
    assert saved['sid'] is None and saved['msgs'][1]['spec']['type'] == '재고 점검' and 'record_type' not in saved['msgs'][1]['spec']
    viewer = Gateway(ops=('read',))
    c2, _ = client(monkeypatch, viewer)
    assert c2.post('/v1/workspaces/7/chats', json={'kind': '업무', 'request': 'x'}).status_code == 403 and viewer.calls == []


def test_chat_missing_column_is_explained(monkeypatch):
    g = Gateway()
    c, _ = client(monkeypatch, g)
    fake_model(monkeypatch, [{'reply': '만들 수 없어요.', 'spec': None, 'missing': ['단가']}])
    out = c.post('/v1/workspaces/7/chats', json={'kind': '지표', 'request': '단가 추이'}).json()
    assert out['messages'][1]['text'] == '단가 칸은 아직 기록에 없어요. 그 값이 적힌 사진이나 CSV를 올리면 만들 수 있어요.'
    assert 'preview' not in out['messages'][1]


def test_recommend_keeps_only_valid_new_rules(monkeypatch):
    g = Gateway()
    c, _ = client(monkeypatch, g)
    good = {'title': '라면 수량 낮음', 'record_type': '재고 점검', 'scope': 'latest', 'reason': 'r',
            'conditions': [{'prop': '수량', 'op': '<', 'value': '15'}]}
    bad = {**good, 'title': '없는 칸', 'conditions': [{'prop': '단가', 'op': '<', 'value': '1'}]}
    fake_model(monkeypatch, [{'automations': [good, bad, {**good}]}])
    assert c.post('/v1/workspaces/7/automations/recommend').json() == {'added': 1}
    proposed = [b for n, b in g.calls if n == 'passo_rule_propose']
    assert len(proposed) == 1 and proposed[0]['rule_kind'] == '업무' and proposed[0]['rule']['type'] == '재고 점검'
    assert [n for n, _ in g.calls][0] == 'passo_log_ai'
