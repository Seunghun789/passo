"""Opt-in real check of 관리: ADMIN_EMAILS 에 넣은 임시 관리자만 [관리]와 관리 화면을 보고, 다른 사람에게는 화면도 숫자도 없다.
API 서버를 ADMIN_EMAILS=<--admin-email> 로 띄운 뒤 실행한다. 만든 임시 계정은 끝나면 지운다."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
 p=argparse.ArgumentParser();p.add_argument('--live',action='store_true',required=True);p.add_argument('--admin-email',required=True)
 p.add_argument('--output',type=Path,required=True);p.add_argument('--api',default='http://localhost:8003');p.add_argument('--web',default='http://localhost:3001')
 a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 v=dict(l.split('=',1) for l in (ROOT/'.env').read_text().splitlines() if '=' in l and not l.startswith('#'))
 url=v['SUPABASE_URL'].strip();secret=v['SUPABASE_SECRET_KEY'].strip()
 admin={'apikey':secret,'Authorization':'Bearer '+secret,'Prefer':'return=representation'}
 c=httpx.Client(timeout=120,trust_env=False);created={'auth':[],'users':[]}
 report={'status':'running','checks':[],'cleanup':False,'started_at':datetime.now(timezone.utc).isoformat()}
 def save():
  t=a.output/'report.tmp';t.write_text(json.dumps(report,ensure_ascii=False,indent=2));t.replace(a.output/'report.json')
 def check(name,condition,**details):
  report['checks'].append({'name':name,'passed':bool(condition),**details});save()
  if not condition:raise AssertionError(name)
 def sb(method,path,**kw):return c.request(method,url+path,headers=admin,**kw)
 def ok(r):
  if not r.is_success:raise RuntimeError('HTTP '+str(r.status_code))
  return r.json() if r.content else None
 def person(email,name):
  pw=secrets.token_urlsafe(24)
  au=ok(sb('POST','/auth/v1/admin/users',json={'email':email,'password':pw,'email_confirm':True,'user_metadata':{'full_name':name}}))
  created['auth'].append(au['id']);save();return {'email':email,'password':pw,'auth':au['id']}
 def cleanup():
  failures=[]
  for aid in created['auth']:
   rows=ok(sb('GET','/rest/v1/auth_identity_links',params={'auth_user_id':f'eq.{aid}','select':'legacy_user_id'}))
   for r in rows:
    for o in ok(sb('GET','/rest/v1/org_members',params={'user_id':f"eq.{r['legacy_user_id']}",'role':'eq.주인','select':'org_id'})):
     if not sb('DELETE','/rest/v1/orgs',params={'id':f"eq.{o['org_id']}"}).is_success:failures.append('orgs')
    if not sb('DELETE','/rest/v1/users',params={'id':f"eq.{r['legacy_user_id']}"}).is_success:failures.append('users')
   if not sb('DELETE','/auth/v1/admin/users/'+aid).is_success:failures.append('auth')
  report['cleanup']={'verified':not failures,'failures':failures};save()
 try:
  boss=person(a.admin_email,'임시 관리자');other=person(a.admin_email.replace('admin','member'),'임시 구성원')
  from playwright.sync_api import sync_playwright
  with sync_playwright() as pw:
   browser=pw.chromium.launch()
   def login(x):
    page=browser.new_page(viewport={'width':1440,'height':1000});page.goto(a.web+'/login')
    page.locator('input[name=email]').fill(x['email']);page.locator('input[name=password]').fill(x['password'])
    page.get_by_role('button',name='이메일로 로그인').click();page.wait_for_url('**/?workspace=**',timeout=60000);return page
   pb=login(boss)
   check('admin sees [관리] in the sidebar',pb.get_by_role('link',name='관리',exact=True).count()==1)
   pb.get_by_role('link',name='관리',exact=True).click();pb.get_by_text('이번 주 활용 워크스페이스').wait_for(timeout=60000)
   check('admin screen shows funnel, ratios and accounts',pb.get_by_text('어디까지 가나').count()==1 and pb.get_by_text('종이 한 장당 AI 비용').count()==1 and pb.locator('tbody tr').count()>=1)
   pb.get_by_text('전체 워크스페이스 보기').click();pb.get_by_role('heading',name='전체 워크스페이스').wait_for(timeout=60000)
   pb.get_by_role('link',name='전체',exact=False).first.click();pb.get_by_role('heading',name='전체 워크스페이스').wait_for(timeout=60000)
   pb.get_by_label('찾기').fill('임시 관리자');pb.get_by_role('button',name='찾기').click();pb.wait_for_load_state()
   check('all workspaces list filters and searches',pb.locator('tbody tr').count()>=1 and all('임시 관리자' in t for t in pb.locator('tbody tr').all_inner_texts()))
   po=login(other)
   check('non-admin has no [관리]',po.get_by_role('link',name='관리',exact=True).count()==0)
   po.goto(a.web+'/admin')
   check('non-admin gets no admin screen',po.get_by_text('이번 주 활용 워크스페이스').count()==0 and po.get_by_text('could not be found').count()>=1)
   browser.close()
  report['status']='passed'
 except Exception as exc:
  report['status']='failed';report['error_type']=type(exc).__name__;save();raise
 finally:
  try:cleanup()
  finally:report['finished_at']=datetime.now(timezone.utc).isoformat();save();c.close()
 print(json.dumps({'status':report['status'],'checks':len(report['checks']),'cleanup':report['cleanup']}))


if __name__=='__main__':main()
