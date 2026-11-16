"""내 계정 · 워크스페이스 만들기 · 워크스페이스 관리(정보 · 구성원 · 초대) · [모두 보기] API.
모두 부른 사람의 JWT 로 DB 함수를 부른다. 누가 무엇을 바꿀 수 있는지는 DB 함수(019)가 정한다."""
import asyncio
from typing import Literal

from fastapi import Depends, HTTPException, Path
from pydantic import BaseModel, ConfigDict, Field

TOKEN = Path(pattern='^[0-9a-f]{64}$')


class NewWorkspace(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    title: str = Field(default='내 워크스페이스', max_length=60)


class Me(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    name: str = Field(min_length=1, max_length=60)
    email: str = Field(default='', max_length=254)
    phone: str = Field(default='', max_length=30)


class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    title: str = Field(min_length=1, max_length=60)
    about: str = Field(default='', max_length=500)
    org: str = Field(default='', max_length=100)
    industry: str = Field(default='', max_length=100)
    product: str = Field(default='', max_length=200)
    website: str = Field(default='', max_length=300)


class Role(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    role: Literal['확인하는 사람', '올리는 사람', '보는 사람']


ROLES = [  # 권한 관리 표: 역할마다 할 수 있는 일
    {'role': '주인', 'can': ['보기', '올리기', '확인 · 반영', '자동화 · 지표', '구성원 초대 · 역할 바꾸기', '워크스페이스 정보']},
    {'role': '확인하는 사람', 'can': ['보기', '올리기', '확인 · 반영', '자동화 · 지표']},
    {'role': '올리는 사람', 'can': ['보기', '올리기']},
    {'role': '보는 사람', 'can': ['보기']},
]


def install_routes(app, session, gateway):
    @app.post('/v1/workspaces', status_code=201)
    async def create_workspace(body: NewWorkspace, token=Depends(session), g=Depends(gateway)):
        """[워크스페이스 생성] · 처음 가입한 사람의 첫 워크스페이스. 같은 조직에 더한다."""
        return {'id': await g.rpc(token, 'passo_workspace_create', {'new_title': body.title.strip() or '내 워크스페이스'})}

    @app.get('/v1/workspaces/summary')
    async def summary(token=Depends(session), g=Depends(gateway)):
        """[모두 보기]: 워크스페이스마다 걸린 건수 · 확인할 것 수."""
        from backend.insights import snapshot
        from backend.workspace import CHECK_KINDS
        from core import engine
        spaces = await g.rpc(token, 'passo_workspaces') or []

        def count(tid):
            S, http = snapshot(g, token, tid)
            try:
                hits = sum(len(engine.run_automation(S['K'], a['spec'])) for a in S['autos'] if a['status'] == '켜짐')
                waiting = [q for q in S['t'].get('proposals', select='kind,evidence', status='eq.대기')
                           if q['kind'] in CHECK_KINDS and (q.get('evidence') or {}).get('user') is not True]
                return {'id': tid, 'hits': hits, 'review': len(waiting), 'records': len(S['K']['records'])}
            finally:
                http.close()
        counts = await asyncio.gather(*(asyncio.to_thread(count, w['id']) for w in spaces[:20]), return_exceptions=True)
        by = {c['id']: c for c in counts if isinstance(c, dict)}
        return [{**w, **by.get(w['id'], {'hits': None, 'review': None, 'records': None})} for w in spaces]

    @app.get('/v1/me')
    async def me(token=Depends(session), g=Depends(gateway)):
        rows = await g.rpc(token, 'passo_me')
        return rows[0] if rows else {}

    @app.post('/v1/me')
    async def save_me(body: Me, token=Depends(session), g=Depends(gateway)):
        """내 계정 [저장]"""
        await g.rpc(token, 'passo_me_update', {'new_name': body.name.strip(), 'new_email': body.email.strip(), 'new_phone': body.phone.strip()})
        return {'ok': True}

    @app.get('/v1/workspaces/{tid}/settings')
    async def settings(tid: int, token=Depends(session), g=Depends(gateway)):
        """워크스페이스 관리: 정보, 권한 관리(역할 표), 구성원, 초대 링크(주인만)."""
        await g.authorize(token, tid)
        info = await g.rpc(token, 'passo_workspace_info', {'tid': tid})
        members = await g.rpc(token, 'passo_members', {'tid': tid})
        invites = await g.rpc(token, 'passo_invites', {'tid': tid}) if info.get('role') == '주인' else []
        return {'info': info, 'members': members, 'invites': [{**i, 'token': i['token']} for i in invites], 'roles': ROLES}

    @app.post('/v1/workspaces/{tid}/settings')
    async def save_settings(tid: int, body: Settings, token=Depends(session), g=Depends(gateway)):
        """워크스페이스 정보 [변경사항 저장하기]"""
        await g.authorize(token, tid)
        await g.rpc(token, 'passo_workspace_update', {'tid': tid, 'new_title': body.title.strip(), 'new_about': body.about, 'org_name': body.org,
                                                      'org_industry': body.industry, 'org_product': body.product, 'org_website': body.website})
        return {'ok': True}

    @app.post('/v1/workspaces/{tid}/members/{uid}')
    async def member_role(tid: int, uid: int, body: Role, token=Depends(session), g=Depends(gateway)):
        """구성원 표에서 역할 바꾸기(주인만)"""
        await g.authorize(token, tid)
        await g.rpc(token, 'passo_member_role', {'tid': tid, 'member': uid, 'new_role': body.role})
        return {'ok': True}

    @app.post('/v1/workspaces/{tid}/invites', status_code=201)
    async def invite(tid: int, body: Role, token=Depends(session), g=Depends(gateway)):
        """[구성원 초대하기] → 역할 → [초대]: 7일 동안 쓸 수 있는 링크 한 개."""
        await g.authorize(token, tid)
        return {'token': await g.rpc(token, 'passo_invite_create', {'tid': tid, 'invite_role': body.role})}

    @app.get('/v1/invites/{tok}')
    async def invite_preview(tok: str = TOKEN, token=Depends(session), g=Depends(gateway)):
        out = await g.rpc(token, 'passo_invite_preview', {'tok': tok})
        if not out:
            raise HTTPException(404, '초대 링크를 찾지 못했어요.')
        return out

    @app.post('/v1/invites/{tok}')
    async def invite_accept(tok: str = TOKEN, token=Depends(session), g=Depends(gateway)):
        """[참여하기]"""
        return {'workspace': await g.rpc(token, 'passo_invite_accept', {'tok': tok})}
