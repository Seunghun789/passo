import hashlib
import io
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from backend.documents import install_routes, original_location
from backend.worker import Worker

BODY = {'request_key':'00000000-0000-4000-8000-000000000001',
        'expected_revision':'a'*32, 'model':'claude-haiku-5-5'}


@pytest.mark.parametrize('method', ['GET', 'POST'])
def test_reread_denied_before_original_download(method):
    class Gateway:
        async def authorize(self, token, tid, action):
            assert (token, tid, action) == ('caller', 7, 'review')
            raise HTTPException(403)
        async def request(self, *args, **kwargs):
            pytest.fail('Unauthorized request reached storage')
    app = FastAPI()
    install_routes(app, lambda:'caller', lambda:Gateway())
    with TestClient(app) as c:
        assert c.request(method, '/v1/workspaces/7/sources/10/reread', json=BODY).status_code == 403


@pytest.mark.parametrize('path', ['uploads/8-10.jpg', 'uploads/7-11.jpg', '../private', 'https://example.com/a.png'])
def test_reread_original_must_bind_tenant_and_source(path):
    with pytest.raises(HTTPException):
        original_location(7, 10, path)


@pytest.mark.parametrize('changes', [{'model':'unknown'}, {'request_key':'bad'}, {'expected_revision':'stale'}, {'storage_path':'user-supplied'}])
def test_reread_input_validation(changes):
    class Gateway:
        async def authorize(self, *args):
            pass
        async def request(self, *args, **kwargs):
            pytest.fail('Invalid body reached storage')
    app = FastAPI()
    install_routes(app, lambda:'caller', lambda:Gateway())
    with TestClient(app) as c:
        assert c.post('/v1/workspaces/7/sources/10/reread', json={**BODY, **changes}).status_code == 422


def test_reread_enqueues_verified_original_with_selected_model():
    image = io.BytesIO()
    Image.new('RGB', (2, 2)).save(image, format='PNG')
    content = image.getvalue()
    class Gateway:
        async def authorize(self, token, tid, action):
            assert (token, tid, action) == ('caller', 7, 'review')
        async def request(self, token, method, path, params):
            assert params == {'tenant_id':'eq.7', 'id':'eq.10', 'select':'storage_path'}
            return httpx.Response(200, json=[{'storage_path':'uploads/7-10.png'}])
        async def original_bytes(self, path, bucket):
            assert (path, bucket) == ('uploads/7-10.png', 'uploads')
            return content
        async def rpc(self, token, name, body):
            assert token == 'caller' and name == 'passo_reread_source'
            assert body == {**BODY, 'tid':7, 'sid':10, 'digest':hashlib.sha256(content).hexdigest(),
                            'size_bytes':len(content), 'mime':'image/png'}
            return {'id':'job', 'status':'queued', 'model_id':body['model'], 'lease_token':'private'}
    app = FastAPI()
    install_routes(app, lambda:'caller', lambda:Gateway())
    with TestClient(app) as c:
        r = c.post('/v1/workspaces/7/sources/10/reread', json=BODY)
        assert r.status_code == 202 and r.json()['model_id'] == BODY['model']
        assert 'lease_token' not in r.json()


def test_worker_uses_selected_model_and_legacy_original(monkeypatch):
    from backend import extraction, documents
    calls = []
    monkeypatch.setattr(documents, 'validate_document', lambda *args:None)
    monkeypatch.setattr(extraction, 'run_ocr', lambda *args:{'1':[]})
    def model(content, mime, selected, hint=''):
        assert (content, mime, selected) == (b'original', 'image/png', 'claude-opus-5-5')
        calls.append('model')
        return {'sheet':{}}
    monkeypatch.setattr(extraction, 'run_model', model)
    monkeypatch.setattr(extraction, 'make_payload', lambda *args:{'records':[{}]})
    monkeypatch.setattr(extraction, 'run_fill', lambda content, mime, sheet, *args, **kw:{'sheet':sheet, 'usage':[]})
    def structure(fetch, tid, sheet, records, selected):
        assert (tid, selected) == (7, 'claude-opus-5-5')
        calls.append('structure')
        return {'type':'점검', 'title':'t', 'props':[], 'links':[], 'samples':{}, 'evidence':{}, 'usage':[]}
    monkeypatch.setattr(extraction, 'run_structure', structure)
    def entities(fetch, tid, structure, records):
        assert tid == 7 and structure['type'] == '점검'
        calls.append('entities')
        return {'classes': [], 'entities': [{'class': '설비', 'name': 'P-03'}], 'same': [], 'usage': []}
    monkeypatch.setattr(extraction, 'run_entities', entities)
    w = Worker.__new__(Worker)
    def request(method, path, **kwargs):
        if path == '/rest/v1/source_inputs':return SimpleNamespace(json=lambda:[{'storage_path':'uploads/7-10.png'}])
        if path == '/rest/v1/passo_checkpoints':return SimpleNamespace(json=lambda:[])
        assert path == '/storage/v1/object/authenticated/uploads/uploads/7-10.png'
        return SimpleNamespace(content=b'original')
    w.request = request
    def rpc(name, body):
        assert name in ('passo_worker_save', 'passo_worker_finish')
        if name == 'passo_worker_finish':
            assert body['payload']['structure']['type'] == '점검' and 'usage' not in body['payload']['structure']
            assert body['payload']['records'][0]['type_name'] == '점검'
            assert body['payload']['entities'] == {'classes': [], 'entities': [{'class': '설비', 'name': 'P-03'}], 'same': []}
        calls.append(name)
        return True
    w.rpc = rpc
    w.process({'id':'job', 'lease_token':'fence', 'tenant_id':7, 'source_input_id':10,
               'sha256':hashlib.sha256(b'original').hexdigest(), 'byte_size':8,
               'media_type':'image/png', 'model_id':'claude-opus-5-5', 'original_bucket':'uploads'})
    assert calls == ['passo_worker_save', 'model', 'passo_worker_save', 'passo_worker_save', 'structure', 'passo_worker_save',
                     'entities', 'passo_worker_save', 'passo_worker_finish']


def test_worker_logs_ai_usage_without_paper_content():
    posted = []
    w = Worker.__new__(Worker)
    w.request = lambda method, path, **kw: posted.append((method, path, kw['json']))
    state = {'extraction': {'sheet': {'rows': ['비밀 값']}, 'usage': {'model': 'claude-sonnet-5-5', 'input_tokens': 1000, 'output_tokens': 200, 'seconds': 4.2}},
             'structure': {'usage': [{'model': 'claude-sonnet-5-5', 'input_tokens': 500, 'output_tokens': 100}]},
             'entities': {'usage': [{'model': 'claude-haiku-5-5', 'input_tokens': 300, 'output_tokens': 30}, {'model': 'gpt-x', 'input_tokens': 1}]}}
    w.log_usage({'id': 'job', 'tenant_id': 7, 'source_input_id': 10}, state)
    method, path, rows = posted[0]
    assert (method, path) == ('POST', '/rest/v1/ai_logs') and len(rows) == 3
    assert [r['prompt'] for r in rows] == ['[워커 읽기] 종이 10', '[워커 구조] 종이 10', '[워커 대상] 종이 10']
    assert rows[0]['duration_ms'] == 4200 and rows[0]['cost_usd'] == 0.004 and all(r['answer'] == '' and r['tenant_id'] == 7 for r in rows)
    assert '비밀 값' not in str(rows) and len({tuple(sorted(r)) for r in rows}) == 1 and rows[1]['duration_ms'] is None
    w.request = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('down'))
    w.log_usage({'id': 'job', 'tenant_id': 7, 'source_input_id': 10}, state)  # 남기지 못해도 멈추지 않는다
