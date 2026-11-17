"""내 계정 · 워크스페이스 관리 API: 입력을 검사하고, 권한은 DB 함수가 정한다."""
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend import account


class Gateway:
    def __init__(self, role='주인'):
        self.role, self.calls = role, []

    async def authorize(self, token, tid, operation='read'):
        if tid == 99:
            raise HTTPException(403, 'no')

    deletion = {'deleted': True, 'blocked': [], 'workspaces': [{'id': 3, 'title': '혼자'}], 'paths': ['3/x/a.png']}
    removed = ()

    async def remove_originals(self, paths):
        self.removed = paths
        return len(paths)

    async def rpc(self, token, name, body=None):
        self.calls.append((name, body))
        if name == 'passo_delete_me':
            return self.deletion if not body['dry_run'] else {**self.deletion, 'deleted': False}
        return {'passo_workspace_create': 12, 'passo_invite_create': 'a' * 64, 'passo_me': [{'name': '나', 'email': None, 'phone': None, 'provider': 'email'}],
                'passo_workspace_info': {'title': 't', 'role': self.role, 'org_owner': self.role == '주인'}, 'passo_members': [{'user_id': 1}],
                'passo_invites': [{'token': 'b' * 64}], 'passo_invite_preview': {'title': 't', 'role': '보는 사람', 'valid': True},
                'passo_invite_accept': 7}.get(name)


def client(g):
    app = FastAPI()
    account.install_routes(app, lambda: 'caller', lambda: g)
    return TestClient(app)


def test_create_workspace_and_me():
    g = Gateway()
    c = client(g)
    assert c.post('/v1/workspaces', json={'title': '  '}).json() == {'id': 12} and g.calls[-1] == ('passo_workspace_create', {'new_title': '내 워크스페이스'})
    assert c.get('/v1/me').json()['name'] == '나'
    assert c.post('/v1/me', json={'name': ' 새 이름 ', 'email': 'a@b.co', 'phone': '010-1'}).status_code == 200
    assert g.calls[-1] == ('passo_me_update', {'new_name': '새 이름', 'new_email': 'a@b.co', 'new_phone': '010-1'})
    assert c.post('/v1/me', json={'name': ''}).status_code == 422


def test_settings_hide_invites_from_non_owner():
    assert client(Gateway()).get('/v1/workspaces/7/settings').json()['invites'] == [{'token': 'b' * 64}]
    g = Gateway(role='보는 사람')
    out = client(g).get('/v1/workspaces/7/settings').json()
    assert out['invites'] == [] and 'passo_invites' not in [n for n, _ in g.calls] and out['roles'][0]['role'] == '주인'
    assert client(Gateway()).get('/v1/workspaces/99/settings').status_code == 403


def test_invites_and_roles_are_checked():
    g = Gateway()
    c = client(g)
    assert c.post('/v1/workspaces/7/invites', json={'role': '보는 사람'}).json() == {'token': 'a' * 64}
    assert c.post('/v1/workspaces/7/invites', json={'role': '주인'}).status_code == 422
    assert c.post('/v1/workspaces/7/members/3', json={'role': '올리는 사람'}).status_code == 200
    assert g.calls[-1] == ('passo_member_role', {'tid': 7, 'member': 3, 'new_role': '올리는 사람'})
    assert c.get('/v1/invites/' + 'c' * 64).json()['valid'] is True
    assert c.get('/v1/invites/not-a-token').status_code == 422
    assert c.post('/v1/invites/' + 'c' * 64).json() == {'workspace': 7}


def test_owner_transfer_and_account_deletion():
    g = Gateway()
    c = client(g)
    assert c.post('/v1/workspaces/7/members/5/owner').json() == {'ok': True} and g.calls[-1] == ('passo_owner_transfer', {'tid': 7, 'member': 5})
    assert c.post('/v1/workspaces/99/members/5/owner').status_code == 403
    preview = c.get('/v1/me/deletion').json()
    assert preview == {'workspaces': [{'id': 3, 'title': '혼자'}], 'blocked': []} and g.calls[-1] == ('passo_delete_me', {'dry_run': True})
    assert c.post('/v1/me/deletion', json={}).status_code == 422 and c.post('/v1/me/deletion', json={'confirm': False}).status_code == 422
    assert c.post('/v1/me/deletion', json={'confirm': True}).json() == {'deleted': True, 'workspaces': 1}
    assert g.calls[-1] == ('passo_delete_me', {'dry_run': False}) and g.removed == ['3/x/a.png']  # DB 에서 지운 뒤 원본 파일도 지운다
    g = Gateway()
    g.deletion = {'deleted': False, 'blocked': [{'id': 7, 'title': '함께'}], 'workspaces': []}
    assert client(g).post('/v1/me/deletion', json={'confirm': True}).status_code == 409 and g.removed == ()
