"""Opt-in real Auth/API/UI check of 가입 · 첫 워크스페이스 · 초대 · 구성원 · 워크스페이스 정보 · 내 계정 · 예전 이메일 계정 잇기.
메일을 보내지 않도록 메일 확인을 마친 임시 계정을 관리 API로 만들고, 끝나면 만든 것을 모두 지운다."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sys
import uuid
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
 p=argparse.ArgumentParser();p.add_argument('--live',action='store_true',required=True)
 p.add_argument('--output',type=Path,required=True);p.add_argument('--api',default='http://localhost:8003');p.add_argument('--web',default='http://localhost:3001')
 a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 v=dict(l.split('=',1) for l in (ROOT/'.env').read_text().splitlines() if '=' in l and not l.startswith('#'))
 url=v['SUPABASE_URL'].strip();secret=v['SUPABASE_SECRET_KEY'].strip();pub=v['SUPABASE_KEY'].strip()
 admin={'apikey':secret,'Authorization':'Bearer '+secret,'Prefer':'return=representation'}
 c=httpx.Client(timeout=120,trust_env=False);run='passo-accounts-probe-'+uuid.uuid4().hex[:12]
 created={'auth':[],'users':[]};report={'status':'running','run':run,'checks':[],'cleanup':False,'started_at':datetime.now(timezone.utc).isoformat()}
 def save():
  t=a.output/'report.tmp';t.write_text(json.dumps(report,ensure_ascii=False,indent=2));t.replace(a.output/'report.json')
 def check(name,condition,**details):
  report['checks'].append({'name':name,'passed':bool(condition),**details});save()
  if not condition:raise AssertionError(name)
 def sb(method,path,**kw):return c.request(method,url+path,headers=admin,**kw)
 def ok(r):
  if not r.is_success:
   report['last_error']={'path':r.request.url.path,'status':r.status_code};save();raise RuntimeError('HTTP '+str(r.status_code))
  return r.json() if r.content else None
 def count(table):
  r=c.head(url+'/rest/v1/'+table,headers={**admin,'Prefer':'count=exact'},params={'select':'id'});r.raise_for_status()
  return int(r.headers['content-range'].split('/')[-1])
 def person(n,name):
  email=f'{run}-{n}@example.com';password=secrets.token_urlsafe(24)
  au=ok(sb('POST','/auth/v1/admin/users',json={'email':email,'password':password,'email_confirm':True,'user_metadata':{'full_name':name}}))
  created['auth'].append(au['id']);save()
  return {'email':email,'password':password,'auth':au['id']}
 def token(x):
  return 'Bearer '+ok(c.post(url+'/auth/v1/token?grant_type=password',headers={'apikey':pub},json={'email':x['email'],'password':x['password']}))['access_token']
 def linked(x):
  rows=ok(sb('GET','/rest/v1/auth_identity_links',params={'auth_user_id':f"eq.{x['auth']}",'select':'legacy_user_id'}))
  return rows[0]['legacy_user_id'] if rows else None
 def cleanup():
  failures=[]
  for uid_ in list(dict.fromkeys(created['users'])):
   orgs=ok(sb('GET','/rest/v1/org_members',params={'user_id':f'eq.{uid_}','role':'eq.주인','select':'org_id'}))
   for o in orgs:  # 이 검증이 만든 조직(과 그 워크스페이스)만 지운다
    if not sb('DELETE','/rest/v1/orgs',params={'id':f"eq.{o['org_id']}"}).is_success:failures.append('orgs')
   if not sb('DELETE','/rest/v1/users',params={'id':f'eq.{uid_}'}).is_success:failures.append('users')
  for ident in created['auth']:
   if not sb('DELETE','/auth/v1/admin/users/'+ident).is_success:failures.append('auth_delete')
  report['after_counts']={t:count(t) for t in ('tenants','users','orgs')}
  report['cleanup']={'verified':not failures and report['after_counts']==report['before_counts'],'failures':failures};save()
 try:
  report['before_counts']={t:count(t) for t in ('tenants','users','orgs')};save()
  A,B=person('a','가입한 주인'),person('b','초대받은 사람')
  check('fresh account is not linked before first login',linked(A) is None)
  from playwright.sync_api import sync_playwright
  with sync_playwright() as pw:
   browser=pw.chromium.launch()
   def login(page,x,path='/login'):
    page.goto(a.web+path);page.locator('input[name=email]').fill(x['email']);page.locator('input[name=password]').fill(x['password'])
    page.get_by_role('button',name='이메일로 로그인').click()
   pa=browser.new_page(viewport={'width':1440,'height':1000})
   login(pa,A);pa.wait_for_url('**view=upload**',timeout=60000)
   check('first login creates a person and opens an empty upload',linked(A) is not None and 'view=upload' in pa.url)
   created['users'].append(linked(A));save()
   tid=int(pa.url.split('workspace=')[1].split('&')[0])
   me=ok(sb('GET','/rest/v1/users',params={'id':f'eq.{linked(A)}','select':'name,provider,sub'}))[0]
   check('person keeps the signup name and email',me['name']=='가입한 주인' and me['provider']=='email' and me['sub']==A['email'])
   ta=token(A);base=f'{a.api}/v1/workspaces/{tid}'
   st=ok(c.get(base+'/settings',headers={'Authorization':ta}))
   check('creator owns the new workspace',st['info']['role']=='주인' and st['info']['org_owner'] is True)
   tok=ok(c.post(base+'/invites',headers={'Authorization':ta},json={'role':'올리는 사람'}))['token']
   pb=browser.new_page(viewport={'width':1440,'height':1000})
   pb.goto(a.web+f'/invite/{tok}');pb.wait_for_url('**/login?next=**',timeout=30000)
   check('invite link asks to log in first','next=%2Finvite%2F' in pb.url or 'next=/invite/' in pb.url)
   pb.locator('input[name=email]').fill(B['email']);pb.locator('input[name=password]').fill(B['password'])
   pb.get_by_role('button',name='이메일로 로그인').click();pb.get_by_role('button',name='참여하기').wait_for(timeout=60000)
   check('invite page shows the workspace and role','올리는 사람' in pb.locator('main').inner_text())
   pb.get_by_role('button',name='참여하기').click();pb.wait_for_url(f'**workspace={tid}**',timeout=60000)
   created['users'].append(linked(B));save()
   tb=token(B)
   spaces=ok(c.get(f'{a.api}/v1/workspaces',headers={'Authorization':tb}))
   check('[참여하기] joins with the invited role',any(w['id']==tid and w['role']=='올리는 사람' for w in spaces))
   check('used invite cannot be used again',c.post(f'{a.api}/v1/invites/{tok}',headers={'Authorization':tb}).status_code==409)
   check('member cannot invite',c.post(base+'/invites',headers={'Authorization':tb},json={'role':'보는 사람'}).status_code==403)
   members=ok(c.get(base+'/settings',headers={'Authorization':ta}))['members']
   bid=next(m['user_id'] for m in members if not m['me'])
   ok(c.post(base+f'/members/{bid}',headers={'Authorization':ta},json={'role':'확인하는 사람'}))
   check('owner changes the member role',any(w['id']==tid and w['role']=='확인하는 사람' for w in ok(c.get(f'{a.api}/v1/workspaces',headers={'Authorization':tb}))))
   pa.goto(a.web+f'/?workspace={tid}&view=settings');pa.get_by_role('heading',name='워크스페이스 정보').wait_for(timeout=60000)
   pa.get_by_label('워크스페이스 이름').fill('검증 가게');pa.get_by_label('하는 일 · 무엇을 기록하나요').fill('재고를 적어요')
   pa.get_by_role('button',name='변경사항 저장하기').click();pa.get_by_text('저장했어요.').wait_for(timeout=30000)
   check('[변경사항 저장하기] saves the workspace info',any(w['id']==tid and w['title']=='검증 가게' for w in ok(c.get(f'{a.api}/v1/workspaces',headers={'Authorization':tb}))))
   pa.get_by_role('button',name='구성원 초대하기').click();pa.get_by_role('button',name='초대',exact=True).click()
   pa.get_by_label('초대 링크').wait_for(timeout=30000)
   check('browser makes an invite link',('/invite/' in pa.get_by_label('초대 링크').input_value()))
   check('member cannot remove others',c.post(base+f'/members/{bid}/remove',headers={'Authorization':tb},json={}).status_code==403)
   pa.on('dialog',lambda d:d.accept())
   pa.locator('tr').filter(has_text='초대받은 사람').get_by_role('button',name='내보내기').click()
   pa.get_by_text('초대받은 사람을(를) 내보냈어요.').wait_for(timeout=30000)
   check('[내보내기] removes the workspace from that person',all(w['id']!=tid for w in ok(c.get(f'{a.api}/v1/workspaces',headers={'Authorization':tb}))))
   check('owner cannot be removed',c.post(base+f'/members/{linked(A)}/remove',headers={'Authorization':ta},json={}).status_code in (403,422))
   pa.screenshot(path=str(a.output/'settings.png'),full_page=True)
   pa.goto(a.web+'/account');pa.get_by_label('휴대폰 번호').fill('010-0000-1111');pa.get_by_role('button',name='저장',exact=True).click()
   pa.get_by_text('저장했어요.').wait_for(timeout=30000)
   check('내 계정 [저장] saves the phone',ok(c.get(f'{a.api}/v1/me',headers={'Authorization':ta}))['phone']=='010-0000-1111')
   pa.goto(a.web+'/workspaces');pa.get_by_text('검증 가게').wait_for(timeout=60000)
   check('[모두 보기] lists workspaces with counts',pa.locator('tbody tr').count()>=1)
   pa.get_by_role('button',name='워크스페이스 생성').click();pa.wait_for_url('**view=upload**',timeout=60000)
   check('[워크스페이스 생성] adds one to the same organization',len(ok(c.get(f'{a.api}/v1/workspaces',headers={'Authorization':ta})))==2)
   # 예전 이메일 계정: 같은 이메일로 가입(메일 확인)하면 그 사람의 기록 · 워크스페이스에 잇는다
   C=person('c','예전 사람')
   legacy=ok(sb('POST','/rest/v1/users',json={'provider':'email','sub':C['email'].upper(),'name':'예전 이름'}))[0]['id']
   created['users'].append(legacy);save()
   pc=browser.new_page();login(pc,C);pc.wait_for_url('**/?workspace=**',timeout=60000)
   check('legacy email account is reused after confirmation',linked(C)==legacy)
   browser.close()
  report['status']='passed'
 except Exception as exc:
  report['status']='failed';report['error_type']=type(exc).__name__;save();raise
 finally:
  try:cleanup()
  finally:report['finished_at']=datetime.now(timezone.utc).isoformat();save();c.close()
 print(json.dumps({'status':report['status'],'checks':len(report['checks']),'cleanup':report['cleanup']}))


if __name__=='__main__':main()
