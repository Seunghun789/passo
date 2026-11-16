"""관리 화면 API: 확인을 마친 관리자 메일만, 아니면 숫자를 세지 않는다."""
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import admin


class Gateway:
    def __init__(self, email, confirmed=True):
        self.user = {'id': 'u', 'email': email, 'email_confirmed_at': '2026-11-01T00:00:00Z' if confirmed else None}

    async def request(self, token, method, path, **kw):
        assert path == '/auth/v1/user'
        return SimpleNamespace(json=lambda: self.user)


def client(g):
    app = FastAPI()
    admin.install_routes(app, lambda: 'caller', lambda: g)
    return TestClient(app)


def test_only_confirmed_admin_emails(monkeypatch):
    monkeypatch.setenv('ADMIN_EMAILS', ' Boss@Example.com , other@example.com')
    ran = []
    from core import db, engine
    monkeypatch.setattr(engine, 'admin_overview', lambda skip=(): ran.append(skip) or {'accounts': [], 'spaces': []})
    monkeypatch.setitem(db.HEADERS, 'apikey', 'sb_secret_test')
    assert client(Gateway('boss@example.com')).get('/v1/admin/me').json() == {'admin': True}
    out = client(Gateway('boss@example.com')).get('/v1/admin').json()
    assert out['stages'][0] == '가입' and ran == [(1, 2, 3, 4)]
    assert client(Gateway('someone@example.com')).get('/v1/admin').status_code == 403
    assert client(Gateway('boss@example.com', confirmed=False)).get('/v1/admin/me').json() == {'admin': False}
    assert len(ran) == 1  # 관리자가 아니면 세지 않는다
    monkeypatch.setitem(db.HEADERS, 'apikey', 'sb_publishable_x')
    assert client(Gateway('boss@example.com')).get('/v1/admin').status_code == 503


def test_no_admins_configured(monkeypatch):
    monkeypatch.delenv('ADMIN_EMAILS', raising=False)
    assert client(Gateway('boss@example.com')).get('/v1/admin/me').json() == {'admin': False}
