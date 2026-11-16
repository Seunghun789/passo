"""관리 화면 API. 관리자는 로그인한 메일(확인을 마친 것)이 서버 환경 변수 ADMIN_EMAILS 에 있는 사람이다.
관리자가 아니면 숫자를 세지 않고 403 을 준다. 모든 워크스페이스를 세야 해서 관리용 키(SUPABASE_SECRET_KEY)로 읽고,
종이 내용 · AI에 보낸 글 · 비밀번호는 돌려주지 않는다(engine.admin_overview)."""
import asyncio
import os

from fastapi import Depends, HTTPException

DEMO = (1, 2, 3, 4)  # 활용 사례 워크스페이스는 세지 않는다


def admins():
    return {e.strip().lower() for e in os.environ.get('ADMIN_EMAILS', '').split(',') if e.strip()}


async def is_admin(g, token):
    user = (await g.request(token, 'GET', '/auth/v1/user')).json()
    email = (user.get('email') or '').strip().lower()
    return bool(email and user.get('email_confirmed_at') and email in admins())


def install_routes(app, session, gateway):
    @app.get('/v1/admin/me')
    async def admin_me(token=Depends(session), g=Depends(gateway)):
        """사이드바에 [관리]를 보일지."""
        return {'admin': await is_admin(g, token)}

    @app.get('/v1/admin')
    async def overview(token=Depends(session), g=Depends(gateway)):
        if not await is_admin(g, token):
            raise HTTPException(403, '관리자만 볼 수 있어요.')
        from core import db, engine
        if not db.HEADERS.get('apikey', '').startswith('sb_secret_'):
            raise HTTPException(503, '관리 화면 설정이 필요해요.')
        o = await asyncio.to_thread(engine.admin_overview, DEMO)
        return {**o, 'stages': engine.STAGES, 'plan': engine.FREE_PLAN}
