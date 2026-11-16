"""Real Next.js browser test with LOCAL fake Auth/API; no live DB or model calls.

Run after npm ci in apps/web. Uses loopback ports 18765/18766 and a headless browser.
DB transitions and real FastAPI boundaries are covered separately in tests/documents.
"""
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import httpx
from PIL import Image
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'artifacts/resume-reread'
WEB = 'http://127.0.0.1:18766'
UPSTREAM = 'http://127.0.0.1:18765'
USER = {'id':'00000000-0000-4000-8000-000000000001', 'aud':'authenticated',
        'role':'authenticated', 'email':'fixture@example.test', 'user_metadata':{'name':'로컬 검증'}}
def b64(value):
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')
TOKEN = b64({'alg':'HS256','typ':'JWT'})+'.'+b64({'sub':USER['id'],'exp':int(time.time())+3600})+'.fixture'
STATE = {'last':1, 'allowed':[1,2], 'confirmed':True, 'reopened':False, 'revision':1, 'job':None, 'finished':False}
PNG = io.BytesIO()
Image.new('RGB', (400, 180), 'white').save(PNG, format='PNG')


def source():
    return {'id':10,'name':'검증용 원본.png','channel':'사진','created_at':time.strftime('%Y-%m-%dT00:00:00Z'),
            'auto':not STATE['reopened'], 'has_original':True, 'rows':int(STATE['confirmed']),
            'wait':int(STATE['reopened'] and not STATE['confirmed']), 'types':['검증 기록'], 'spans':{}}


def records():
    return [{'id':12 if STATE['finished'] else 11, 'type_name':'검증 기록','occurred_at':'2026-11-16',
             'data':{'수량':{'raw':22 if STATE['finished'] else 11,'value':22 if STATE['finished'] else 11,'status':'value'}},
             'status':'확정' if STATE['confirmed'] else '대기','source_input_id':10,'source_row':0}]


def proposals():
    return [{'id':22 if STATE['finished'] else 21,'kind':'읽은 값', 'source_input_id':10,
             'payload':{'type':'검증 기록','rows':1,'reopened':True}}] if STATE['reopened'] and not STATE['confirmed'] else []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, body, status=200, mime='application/json'):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/auth/v1/user':return self.respond(USER)
        if path == '/v1/workspaces':return self.respond([{'id':n,'title':f'검증 공간 {n}','role':'확인하는 사람'} for n in sorted(STATE['allowed'], key=lambda n:n!=STATE['last'])])
        if path.endswith('/original'):return self.respond(PNG.getvalue(), mime='image/png')
        if path.endswith('/overview'):return self.respond({'record_count':int(STATE['confirmed']),'review_count':len(proposals()),'period':'이번 주','range':[],
            'sources':[source()], 'recent':[], 'types':[{'name':'검증 기록','count':int(STATE['confirmed']),'current':int(STATE['confirmed']),'previous':0,'last':'2026-11-16'}],
            'properties':[], 'aliases':[]})
        if path.endswith('/documents'):
            job = STATE['job']
            if job and time.monotonic()-STATE['started']>3 and not STATE['finished']:
                job['status']='succeeded';STATE['finished']=True;STATE['revision']+=1
            return self.respond([job] if job else [])
        if path.endswith('/reviews'):return self.respond({'items':proposals(),'next':None})
        if path.endswith('/records'):return self.respond({'items':records() if STATE['confirmed'] else [],'next':None})
        if path.endswith('/audit'):return self.respond({'items':[],'next':None})
        if path.endswith('/sources/10'):return self.respond({**source(), 'records':records()})
        if path.endswith('/sources/10/review'):return self.respond({'revision':f"{STATE['revision']:032x}",'records':records(),'can_reopen':STATE['confirmed']})
        if path.endswith('/sources/10/reread'):return self.respond({'revision':f"{STATE['revision']:032x}",'can_reread':not STATE['confirmed'],
            'models':['claude-haiku-5-5','claude-sonnet-5-5','claude-opus-5-5'],'default_model':'claude-sonnet-5-5'})
        return self.respond({'detail':'fixture route missing'},404)

    def do_POST(self):
        path = urlparse(self.path).path
        body = json.loads(self.rfile.read(int(self.headers.get('content-length', '0'))) or b'{}')
        if path == '/auth/v1/token':return self.respond({'access_token':TOKEN,'refresh_token':'fixture-refresh','token_type':'bearer','expires_in':3600,'user':USER})
        if path == '/auth/v1/logout':return self.respond({})
        if path.endswith('/opened'):
            STATE['last']=int(path.split('/')[3]);return self.respond(True)
        if path.endswith('/reopen'):
            STATE.update(confirmed=False,reopened=True);STATE['revision']+=1;return self.respond({'review_id':21})
        if path.endswith('/reread'):
            if STATE['confirmed']:return self.respond({},409)
            STATE['started']=time.monotonic()
            STATE['job']={'id':'00000000-0000-4000-8000-000000000010','status':'queued','source_input_id':10,
                          'model_id':body['model'],'reread_revision':body['expected_revision']}
            return self.respond(STATE['job'],202)
        if path.endswith('/read'):
            STATE['confirmed']=True;STATE['revision']+=1;return self.respond({})
        return self.respond({},404)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report={'environment':'Headless Chromium + actual Next.js; local fixture Auth/API, no live Supabase or model', 'checks':[]}
    def check(name, result):
        assert result, name
        report['checks'].append({'name':name,'passed':True})
    server=ThreadingHTTPServer(('127.0.0.1',18765),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    log=(OUT/'next-ui.log').open('w')
    process=subprocess.Popen(['npm','run','dev','--','--port','18766'],cwd=ROOT/'apps/web',stdout=log,stderr=log,
                             env={**os.environ,'SUPABASE_URL':UPSTREAM,'SUPABASE_PUBLISHABLE_KEY':'fixture-public','PASSO_API_URL':UPSTREAM},start_new_session=True)
    try:
        for _ in range(120):
            try:
                if httpx.get(WEB+'/login').status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.5)
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page(viewport={'width':1440,'height':1000})
            page.set_default_timeout(20000)
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            def login():
                page.goto(WEB+'/login')
                page.get_by_label('이메일',exact=True).fill('fixture@example.test')
                page.get_by_label('비밀번호',exact=True).fill('fixture-password')
                page.get_by_role('button',name='이메일로 로그인').click()
                page.wait_for_url('**/?workspace=*&view=home')
            login()
            check('no visit defaults to first accessible home','workspace=1' in page.url)
            with page.expect_response(lambda r:'/business/opened' in r.url and r.status==200):
                page.goto(WEB+'/?workspace=2&view=records')
            page.goto(WEB+'/')
            page.wait_for_url('**/?workspace=2&view=home')
            check('bare URL restores last visited workspace home',True)
            page.locator('.account summary').click()
            page.get_by_role('button',name='로그아웃',exact=True).click()
            page.wait_for_url('**/login')
            login()
            check('logout and relogin restore last workspace','workspace=2' in page.url)
            page.goto(WEB+'/?workspace=999')
            expect(page.get_by_text('연결된 워크스페이스가 없거나 접근할 수 없어요.')).to_be_visible()
            check('invalid explicit workspace does not change saved visit',STATE['last']==2)
            page.goto(WEB+'/?workspace=2&view=review')
            page.get_by_text('자동 반영한 최근 문서 · 7일 안에 다시 확인',exact=True).click()
            page.get_by_role('button',name='다시 확인할 내용 보기').click()
            page.get_by_role('button',name='다시 확인으로 돌리기',exact=True).click()
            expect(page.locator('.review-card')).to_contain_text('수량: 11')
            check('reopen exposes existing values for review',not STATE['confirmed'])
            page.get_by_role('button',name='← 올리기로').click()
            page.get_by_role('tab',name='올린 종이 1',exact=True).click()
            page.get_by_role('button',name='보기',exact=True).click()
            page.get_by_role('button',name='다시 읽기',exact=True).click()
            page.get_by_label('읽는 모델',exact=True).select_option('claude-opus-5-5')
            page.screenshot(path=str(OUT/'model-selection.png'),full_page=True)
            page.get_by_role('button',name='읽기 시작',exact=True).click()
            expect(page.get_by_role('heading',name='확인할 것 1개')).to_be_visible()
            check('reread navigates to review with chosen model',STATE['job']['model_id']=='claude-opus-5-5')
            expect(page.locator('.review-card')).to_contain_text('수량: 22',timeout=20000)
            check('polling replaces old card with newly extracted values',page.locator('.review-card').get_by_text('수량: 11').count()==0)
            page.screenshot(path=str(OUT/'fresh-review.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            check('mobile review has no page overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            page.get_by_role('button',name='내용 확인 후 확정',exact=True).click()
            expect(page.get_by_role('heading',name='지금 확인할 것은 다 봤어요')).to_be_visible()
            check('new read card can be confirmed',STATE['confirmed'])
            STATE['allowed']=[1]
            page.goto(WEB+'/')
            page.wait_for_url('**/?workspace=1&view=home')
            check('lost membership falls back to allowed workspace',True)
            response=page.request.post(WEB+'/api/workspaces/1/business/opened',data='{}',headers={'Origin':'https://foreign.example'})
            check('web proxy rejects cross origin writes',response.status==403)
            check('no uncaught browser runtime errors',not errors)
            browser.close()
        report['passed']=True
    except Exception as e:
        report.update(passed=False,error=str(e))
        raise
    finally:
        (OUT/'browser.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
        import signal
        os.killpg(process.pid,signal.SIGTERM)
        process.wait(timeout=15);log.close();server.shutdown()
    print(json.dumps({'passed':True,'checks':len(report['checks'])}))


if __name__=='__main__':
    main()
