import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.workspace import install_routes

RULE = {'heads': [{'written': '현수', 'means': '현수막'}, {'written': '현', 'means': '현수막'}], 'head_col': '품목', 'number_col': '폭'}
CARD = {'id': 5, 'source_input_id': 10, 'payload': {'type': '거래 내역', 'label': '품명', 'written': '현수 \\700', 'guess': RULE}}
RECORDS = [{'id': 1, 'source_input_id': 10, 'data': {'품명': {'raw': '현수 \\700'}}},
           {'id': 2, 'source_input_id': 9, 'data': {'품명': {'raw': '현 \\500'}}},
           {'id': 3, 'source_input_id': 10, 'data': {'품명': {'raw': '개 \\914'}}}]


def gateway(calls, card=CARD):
    class Gateway:
        async def authorize(self, token, tid, action=None):
            assert (token, tid, action) == ('caller', 7, 'review')
        async def request(self, token, method, path, params=None, **kw):
            assert params['tenant_id'] == 'eq.7'
            if path == '/rest/v1/proposals':
                assert params['kind'] == 'eq.뜻 확인' and params['status'] == 'eq.대기'
                return httpx.Response(200, json=[card] if card else [])
            assert path == '/rest/v1/records' and params['type_name'] == 'eq.거래 내역'
            return httpx.Response(200, json=RECORDS if params['id'] == 'gt.0' else [])
        async def rpc(self, token, name, body):
            calls.append((name, body))
            return True
    return Gateway()


def client(calls, card=CARD):
    app = FastAPI()
    install_routes(app, lambda: 'caller', lambda: gateway(calls, card))
    return TestClient(app)


def test_guess_preview_counts_rows_without_ai():
    calls = []
    with client(calls) as c:
        r = c.post('/v1/workspaces/7/meanings/5/preview', json={})
    assert r.status_code == 200 and calls == []
    body = r.json()
    assert body['rows'] == 2 and body['here'] == 1 and body['before'] == 1
    assert body['sample'][0] == {'written': '현수 \\700', '품목': '현수막', '폭': 700}


def test_apply_recounts_on_server_and_writes_only_rule_columns():
    calls = []
    with client(calls) as c:
        r = c.post('/v1/workspaces/7/meanings/5/apply', json={'rule': RULE})
    assert r.status_code == 200 and r.json() == {'rows': 2}
    name, body = calls[0]
    assert name == 'passo_apply_meaning' and body['changes'] == {'1': {'품목': '현수막', '폭': 700}, '2': {'품목': '현수막', '폭': 500}}
    assert body['said'] is None


def test_apply_rejects_rule_that_overwrites_the_written_column():
    calls = []
    with client(calls) as c:
        r = c.post('/v1/workspaces/7/meanings/5/apply', json={'rule': {**RULE, 'head_col': '품명'}})
    assert r.status_code == 422 and calls == []


def test_answered_card_is_conflict():
    calls = []
    with client(calls, card=None) as c:
        assert c.post('/v1/workspaces/7/meanings/5/apply', json={'rule': RULE}).status_code == 409
