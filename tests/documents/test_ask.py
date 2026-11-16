"""묻기 API: 권한을 먼저 확인하고, 숫자는 기록에서 세며, 사용 기록을 남긴다."""
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend import ask as ask_module
from backend.structure import Reader
from core.record_cells import encode_record

TABLES = {
    'object_types': [{'name': '재고 점검', 'kind': '기록', 'parent_name': None, 'trust': None}],
    'property_defs': [{'type_name': '재고 점검', 'name': '품목', 'dtype': 'text', 'unit': None, 'description': None, 'is_entity': True, 'ref_class': None, 'position': 0},
                      {'type_name': '재고 점검', 'name': '수량', 'dtype': 'number', 'unit': '개', 'description': None, 'is_entity': False, 'ref_class': None, 'position': 1}],
    'alias_dict': [{'type_name': '재고 점검', 'alias': a, 'prop_name': p} for a, p in (('품목', '품목'), ('수량', '수량'), ('수량(개)', '수량'))],
    'records': [encode_record({'id': i, 'type_name': '재고 점검', 'occurred_at': '2026-11-16', 'photo_path': None, 'source_input_id': 1, 'data': d})
                for i, d in ((1, {'품목': '생수', '수량(개)': '40'}), (2, {'품목': '라면', '수량': '12'}), (3, {'품목': '과자', '수량': '-'}))],
}


class Gateway:
    url, key = 'https://example.invalid', 'sb_publishable_x'

    def __init__(self, allowed=True):
        self.allowed, self.logged = allowed, []

    async def authorize(self, token, tid):
        if not self.allowed:
            raise HTTPException(403, 'no')

    async def rpc(self, token, name, body):
        assert name == 'passo_log_ai' and token == 'caller'
        self.logged.append(body)


def client(monkeypatch, g, replies=(), tables=TABLES):
    seen = {'closed': 0, 'requests': []}
    def open_reader(gateway, token, tid):
        assert (token, tid) == ('caller', 7)
        return Reader(lambda table, params: tables.get(table, []), tid), SimpleNamespace(close=lambda: seen.__setitem__('closed', seen['closed'] + 1))
    monkeypatch.setattr(ask_module, 'open_reader', open_reader)
    queue = list(replies)
    class Fake:
        def __init__(self, **kw): seen['connect'] = kw
        def __enter__(self): return self
        def __exit__(self, *a): pass
        @property
        def messages(self):
            def create(**kw):
                seen['requests'].append(kw)
                r = queue.pop(0)
                if isinstance(r, Exception): raise r
                return r
            return SimpleNamespace(create=create)
    import anthropic
    monkeypatch.setattr(anthropic, 'Anthropic', Fake)
    monkeypatch.setenv('RUNYOUR_API_KEY', 'k')
    app = FastAPI()
    ask_module.install_routes(app, lambda: 'caller', lambda: g)
    return TestClient(app), seen


def reply(stop, *content, used=(100, 20)):
    return SimpleNamespace(stop_reason=stop, content=list(content), usage=SimpleNamespace(input_tokens=used[0], output_tokens=used[1]))


def test_answer_counts_from_records_and_logs_usage(monkeypatch):
    g = Gateway()
    tool = SimpleNamespace(type='tool_use', id='t1', name='aggregate', input={'type': '재고 점검', 'fn': 'sum', 'prop': '수량'})
    c, seen = client(monkeypatch, g, [reply('tool_use', tool), reply('end_turn', SimpleNamespace(type='text', text='수량 합계는 52개예요.'))])
    r = c.post('/v1/workspaces/7/ask', json={'question': ' 수량 합계는? '})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out['question'] == '수량 합계는?' and out['text'] == '수량 합계는 52개예요.'
    assert out['how'] == ['재고 점검 · 수량 합계 · 확인된 수량 2칸 · 미확정 1칸']
    assert [e['_id'] for e in out['evidence']] == [1, 2, 3] and out['evidence'][0]['수량'] == '40' and out['evidence'][2].get('수량') in (None, '-')  # 근거 표는 적힌 그대로, 미확정 칸은 값이 없다
    sent = seen['requests'][1]['messages'][-1]['content'][0]['content']
    assert '"결과": 52' in sent  # 숫자는 코드가 세어 AI에게 준 것
    assert seen['connect']['base_url'] == 'https://api.runyour.ai' and seen['closed'] == 1
    assert g.logged == [{'tid': 7, 'model': 'claude-sonnet-5-5', 'prompt': '[묻기] 수량 합계는?', 'answer': '수량 합계는 52개예요.',
                         'input_tokens': 200, 'output_tokens': 40, 'cost_usd': 0.0008, 'duration_ms': g.logged[0]['duration_ms']}]


def test_options_examples_use_confirmed_names(monkeypatch):
    c, _ = client(monkeypatch, Gateway())
    out = c.get('/v1/workspaces/7/ask').json()
    assert out['default_model'] == 'claude-sonnet-5-5' and out['has_records']
    assert out['examples'] == ['이번 주 재고 점검 몇 건?', '품목별 수량 가장 큰 값은?']


@pytest.mark.parametrize('body,status', [({'question': ''}, 422), ({'question': 'q', 'model': 'gpt'}, 422), ({'question': 'q' * 501}, 422), ({'question': 'q', 'extra': 1}, 422)])
def test_bad_requests_never_reach_the_model(monkeypatch, body, status):
    c, seen = client(monkeypatch, Gateway())
    assert c.post('/v1/workspaces/7/ask', json=body).status_code == status and seen['requests'] == []


def test_forbidden_workspace_reads_nothing(monkeypatch):
    c, seen = client(monkeypatch, Gateway(allowed=False))
    assert c.post('/v1/workspaces/7/ask', json={'question': 'q'}).status_code == 403
    assert c.get('/v1/workspaces/7/ask').status_code == 403 and seen['closed'] == 0


def test_empty_workspace_and_provider_failure(monkeypatch):
    g = Gateway()
    c, seen = client(monkeypatch, g, tables={})
    assert c.post('/v1/workspaces/7/ask', json={'question': 'q'}).status_code == 409 and seen['requests'] == []
    import anthropic
    class Down(anthropic.APIError):
        def __init__(self): pass
    c, seen = client(monkeypatch, g, [Down()])
    r = c.post('/v1/workspaces/7/ask', json={'question': 'q'})
    assert r.status_code == 503 and g.logged == [] and seen['closed'] == 1
