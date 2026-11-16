"""Opt-in real Auth/API/UI/model check of 홈·대시보드·자동화 with scoped temporary fixtures and verified cleanup."""
import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
import sys
import time
import uuid
import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
 p=argparse.ArgumentParser();p.add_argument('--live',action='store_true',required=True)
 p.add_argument('--output',type=Path,required=True);p.add_argument('--api',default='http://localhost:8003')
 p.add_argument('--web',default='http://localhost:3001')
 a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 from core.record_cells import encode_record
 v=dict(l.split('=',1) for l in (ROOT/'.env').read_text().splitlines() if '=' in l and not l.startswith('#'))
 url=v['SUPABASE_URL'].strip();secret=v['SUPABASE_SECRET_KEY'].strip();pub=v['SUPABASE_KEY'].strip()
 admin={'apikey':secret,'Authorization':'Bearer '+secret,'Prefer':'return=representation'}
 c=httpx.Client(timeout=120,trust_env=False);run='passo-insights-probe-'+uuid.uuid4().hex
 created={'auth':[],'users':[],'tenants':[]}
 report={'status':'running','run':run,'api':a.api,'web':a.web,'checks':[],'cleanup':False,'started_at':datetime.now(timezone.utc).isoformat()}
 def save():
  temp=a.output/'report.tmp';temp.write_text(json.dumps(report,ensure_ascii=False,indent=2));temp.replace(a.output/'report.json')
 def check(name,condition,**details):
  report['checks'].append({'name':name,'passed':bool(condition),**details});save()
  if not condition:raise AssertionError(name)
 def sb(method,path,**kw):return c.request(method,url+path,headers=admin,**kw)
 def ok(r):
  if not r.is_success:
   report['last_error']={'path':r.request.url.path,'status':r.status_code};save();raise RuntimeError('HTTP '+str(r.status_code))
  return r.json() if r.content else None
 def post(table,data):return ok(sb('POST','/rest/v1/'+table,json=data))[0]
 def count(table):
  r=c.head(url+'/rest/v1/'+table,headers={**admin,'Prefer':'count=exact'},params={'select':'id'});r.raise_for_status()
  return int(r.headers['content-range'].split('/')[-1])
 def cleanup():
  failures=[]
  for tid in created['tenants']:  # ai_logs 는 워크스페이스를 지워도 남으므로 이 검증이 만든 줄만 먼저 지운다
   if not sb('DELETE','/rest/v1/ai_logs',params={'tenant_id':f'eq.{tid}'}).is_success:failures.append('ai_logs')
  for table in ['tenants','users']:
   for ident in created[table]:
    if not sb('DELETE','/rest/v1/'+table,params={'id':f'eq.{ident}'}).is_success:failures.append(table)
    if ok(sb('GET','/rest/v1/'+table,params={'id':f'eq.{ident}','select':'id'})):failures.append('remaining_'+table)
  for ident in created['auth']:
   if not sb('DELETE','/auth/v1/admin/users/'+ident).is_success:failures.append('auth_delete')
   if sb('GET','/auth/v1/admin/users/'+ident).status_code!=404:failures.append('remaining_auth')
  report['after_counts']={t:count(t) for t in ('records','tenants','users')}
  report['cleanup']={'verified':not failures and report['after_counts']==report['before_counts'],'failures':failures,'created':created};save()
 try:
  report['before_counts']={t:count(t) for t in ('records','tenants','users')};save();accounts=[]
  for n in range(3):
   email=run+str(n)+'@example.com';password=secrets.token_urlsafe(32)
   au=ok(sb('POST','/auth/v1/admin/users',json={'email':email,'password':password,'email_confirm':True}));created['auth'].append(au['id']);save()
   u=post('users',{'provider':'email','sub':email,'name':run});created['users'].append(u['id']);save()
   post('auth_identity_links',{'auth_user_id':au['id'],'legacy_user_id':u['id']})
   token=ok(c.post(url+'/auth/v1/token?grant_type=password',headers={'apikey':pub},json={'email':email,'password':password}))['access_token']
   accounts.append({'id':u['id'],'email':email,'password':password,'Authorization':'Bearer '+token})
  for n in range(2):
   t=post('tenants',{'name':run+str(n),'title':'자동화 검증'});created['tenants'].append(t['id']);save()
  post('memberships',{'tenant_id':created['tenants'][0],'user_id':accounts[0]['id'],'role':'주인'})
  post('memberships',{'tenant_id':created['tenants'][0],'user_id':accounts[1]['id'],'role':'보는 사람'})
  post('memberships',{'tenant_id':created['tenants'][1],'user_id':accounts[2]['id'],'role':'주인'})
  tid=created['tenants'][0];T='재고 점검';day=lambda n:(date.today()-timedelta(days=n)).isoformat()
  post('object_types',{'tenant_id':tid,'name':T,'kind':'기록'})
  for i,(name,dtype,unit,ent) in enumerate((('품목','text',None,True),('수량','number','개',False),('다음 점검','date',None,False))):
   post('property_defs',{'tenant_id':tid,'type_name':T,'name':name,'dtype':dtype,'unit':unit,'is_entity':ent,'position':i})
   post('alias_dict',{'tenant_id':tid,'type_name':T,'alias':name,'prop_name':name})
  # 생수는 이틀마다 들어오다 열흘째 없고, 라면은 오늘도 들어왔다 → '재고 점검 4일 넘게 없음'에 생수만 걸린다
  rows=[('생수',n,str(40-n)) for n in (10,12,14,16)]+[('라면',n,'12') for n in (0,2,4,6)]
  ok(sb('POST','/rest/v1/records',json=[encode_record({'tenant_id':tid,'type_name':T,'occurred_at':day(n),'status':'확정','data':{'품목':x,'수량':q,'다음 점검':day(n-7)}}) for x,n,q in rows]))
  post('object_types',{'tenant_id':created['tenants'][1],'name':T,'kind':'기록'})
  ok(sb('POST','/rest/v1/records',json=[encode_record({'tenant_id':created['tenants'][1],'type_name':T,'occurred_at':day(30),'status':'확정','data':{'품목':'남의 것','수량':'900'}})]))
  owner,viewer,other=({'Authorization':x['Authorization']} for x in accounts);base=f'{a.api}/v1/workspaces/{tid}';GAP=f'{T} 4일 넘게 없음'
  check('unauthenticated automations denied',c.get(base+'/automations').status_code==401)
  check('foreign workspace automations denied',c.get(base+'/automations',headers=other).status_code==403)
  auto=ok(c.get(base+'/automations',headers=owner));s=next((x for x in auto['suggestions'] if x['title']==GAP),None)
  check('gap suggestion counts the missing item',s and s['count']==1 and [r['values']['품목'] for r in s['evidence']['rows']]==['생수'],suggestions=[x['title'] for x in auto['suggestions']])
  check('viewer sees but cannot turn on',ok(c.get(base+'/automations',headers=viewer))['can_edit'] is False and c.post(base+'/automations',headers=viewer,json={'title':GAP}).status_code==403)
  check('unknown rule title is refused',c.post(base+'/automations',headers=owner,json={'title':'남이 만든 규칙'}).status_code==409)
  aid=ok(c.post(base+'/automations',headers=owner,json={'title':GAP}))['id']
  stored=ok(sb('GET','/rest/v1/automations',params={'tenant_id':f'eq.{tid}','select':'id,spec,status'}))
  check('owner turns it on with the server rule',len(stored)==1 and stored[0]['id']==aid and stored[0]['status']=='켜짐' and stored[0]['spec']['conditions'][0]['op']=='older_than_days')
  home=ok(c.get(base+'/home',headers=viewer))
  check('home shows the alert to the viewer',home['enabled']==1 and home['alerts'][0]['headline']=='생수 기록이 10일째 없어요',headline=home['alerts'][0].get('headline') if home['alerts'] else None)
  check('home glance counts this week from records',home['glance'][0]['value']=='4' and home['glance'][0]['previous']=='2',glance=home['glance'])
  dash=ok(c.get(base+'/dashboard',headers=owner,params={'period':'이번 달'}))
  check('dashboard draws counts and trend',{w['title'] for w in dash['auto']}>={f'{T} 기록 수',f'{T} · 수량 추이'})
  check('foreign rows never counted',all('남의 것' not in json.dumps(w,ensure_ascii=False) for w in dash['auto']))
  from playwright.sync_api import sync_playwright
  with sync_playwright() as pw:
   browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1050})
   page.goto(a.web+'/login');page.locator('input[name=email]').fill(accounts[0]['email']);page.locator('input[name=password]').fill(accounts[0]['password'])
   page.get_by_role('button',name='이메일로 로그인').click();page.locator('.workspace-main h1').wait_for(timeout=60000)
   page.goto(a.web+f'/?workspace={tid}&view=home');page.locator('.alert h3').wait_for(timeout=60000)
   check('browser home shows the alert card',page.locator('.alert h3').inner_text()=='생수 기록이 10일째 없어요' and '오늘 챙길 것은 1가지예요' in page.locator('.greeting').inner_text())
   page.get_by_role('button',name='이번 주 요약 만들기').click();page.locator('.week p').first.wait_for(timeout=180000)
   check('weekly summary shows sentences with evidence',page.locator('.week p').count()>=1 and page.locator('.week .proof summary').count()>=1)
   page.screenshot(path=str(a.output/'home.png'),full_page=True)
   page.goto(a.web+f'/?workspace={tid}&view=automation');page.get_by_role('button',name='끄기').wait_for(timeout=60000)
   page.get_by_role('button',name='끄기').click();page.get_by_text('껐어요. 홈에서 빠져요.').wait_for(timeout=60000)
   check('turning off moves it to the off list',page.get_by_text('꺼 둔 자동화 1개').count()==1 and page.get_by_role('button',name='끄기').count()==0)
   page.screenshot(path=str(a.output/'automation.png'),full_page=True)
   page.goto(a.web+f'/?workspace={tid}&view=dashboard');page.get_by_text('기록 현황').wait_for(timeout=60000)
   page.locator('.vega svg').first.wait_for(timeout=60000);check('browser dashboard shows the trend chart',page.locator('.vega svg').count()>=1)
   page.get_by_role('button',name='만들기',exact=True).click();page.get_by_role('tab',name='말로 만들기').click()
   page.get_by_label('말로 만들기').fill('품목별 수량 평균을 막대 그래프로');page.get_by_role('button',name='보내기').click()
   page.locator('.msg.assistant .vega svg').first.wait_for(timeout=180000)
   check('dashboard chat draws a preview from records',page.locator('.msg.assistant .vega svg').count()>=1)
   page.locator('.msg.assistant .card-actions button',has_text='올리기').first.click();page.get_by_text('대시보드에 올렸어요.').first.wait_for(timeout=60000)
   page.get_by_role('tab',name='보기 고르기').click();page.locator('.make .widget-grid .widget').first.wait_for(timeout=60000)
   check('view picker shows tiles drawn from records',page.locator('.make .widget-grid .widget').count()>=3)
   page.screenshot(path=str(a.output/'dashboard.png'),full_page=True);browser.close()
  check('home is quiet after turning off',ok(c.get(base+'/home',headers=owner))['enabled']==0)
  widgets=ok(sb('GET','/rest/v1/widgets',params={'tenant_id':f'eq.{tid}','select':'id,spec,status'}))
  check('chat view is put up on the dashboard',any(w['spec'].get('kind')=='view' for w in widgets),widgets=[w['spec'].get('title') for w in widgets])
  dash=ok(c.get(base+'/dashboard',headers=owner,params={'period':'이번 달'}))
  cal=next((v for v in dash['gallery'] if v.get('shape')=='달력'),None)
  check('view picker offers a calendar from the future-date field',cal is not None,shapes=[v.get('shape') for v in dash['gallery']])
  wid=ok(c.post(base+'/widgets',headers=owner,json={'title':cal['title'],'source':'gallery'}))['id']
  moved=ok(c.get(base+f'/widgets/{wid}/calendar',headers=owner,params={'mode':'month','offset':'1'}))
  check('calendar moves to the next month',moved['kind']=='calendar' and moved['offset']==1 and len(moved['days'])>=28)
  pick={'type':T,'shape':'막대','fn':'avg','prop':'수량','by':'품목'}
  prev=ok(c.post(base+'/widgets/preview',headers=owner,params={'period':'올해'},json={'pick':pick}))
  check('pick preview counts in code',{r['묶음']:r['값'] for r in prev['view']['vega']['data']['values']}=={'생수':27.0,'라면':12.0},how=prev.get('how'))
  check('client-made rule is refused',c.post(base+'/widgets',headers=owner,json={'title':'가짜','source':'pick','pick':{**pick,'by':'없는 칸'}}).status_code==422)
  started=time.monotonic();r=c.post(base+'/chats',headers=owner,json={'kind':'업무','request':'수량이 15보다 적으면 먼저 볼 것에 올려 줘'})
  check('automation chat answers with a rule',r.status_code==200 and any(m.get('preview') for m in r.json()['messages']),status=r.status_code,seconds=round(time.monotonic()-started,1))
  talk=r.json();m=next(m for m in talk['messages'] if m.get('preview'))
  check('chat rule counts current hits',m['preview']['count']>=1,count=m['preview']['count'],title=m['title'])
  ok(c.post(base+'/automations',headers=owner,json={'title':m['title'],'source':'chat','chat_id':talk['id'],'index':m['index']}))
  listed=ok(c.get(base+'/chats',headers=owner,params={'kind':'업무'}))
  check('chat shows it was turned on',listed[0]['made'] is True)
  check('another member cannot see my chats',c.get(base+'/chats',headers=viewer,params={'kind':'업무'}).status_code==403)
  ok(c.post(base+f'/chats/{talk["id"]}',headers=owner,json={'action':'drop'}))
  check('dropped chat can be restored',ok(c.get(base+'/chats',headers=owner,params={'kind':'업무'}))[0]['deleted_at'] is not None)
  ok(c.post(base+f'/chats/{talk["id"]}',headers=owner,json={'action':'restore'}))
  rec=ok(c.post(base+'/automations/recommend',headers=owner))
  auto=ok(c.get(base+'/automations',headers=owner))
  check('AI recommendations become cards',len([s for s in auto['suggestions'] if s.get('source')=='proposal'])==rec['added'],added=rec['added'])
  logs=ok(sb('GET','/rest/v1/ai_logs',params={'tenant_id':f'eq.{tid}','select':'model,input_tokens,output_tokens,cost_usd,duration_ms'}))
  check('every AI call is recorded',len(logs)>=4 and all(l['input_tokens']>0 for l in logs),calls=len(logs),cost=round(sum(float(l['cost_usd']) for l in logs),4))
  report['status']='passed'
 except Exception as exc:
  report['status']='failed';report['error_type']=type(exc).__name__;save();raise
 finally:
  try:cleanup()
  finally:report['finished_at']=datetime.now(timezone.utc).isoformat();save();c.close()
 print(json.dumps({'status':report['status'],'checks':len(report['checks']),'cleanup':report['cleanup']}))


if __name__=='__main__':main()
