"""Opt-in real Auth/API/UI/model check of 묻기 with scoped temporary fixtures and verified cleanup."""
import argparse
from datetime import date, datetime, timezone
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
 c=httpx.Client(timeout=120,trust_env=False);run='passo-ask-probe-'+uuid.uuid4().hex
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
  for n in range(2):
   email=run+str(n)+'@example.com';password=secrets.token_urlsafe(32)
   au=ok(sb('POST','/auth/v1/admin/users',json={'email':email,'password':password,'email_confirm':True}));created['auth'].append(au['id']);save()
   u=post('users',{'provider':'email','sub':email,'name':run});created['users'].append(u['id']);save()
   post('auth_identity_links',{'auth_user_id':au['id'],'legacy_user_id':u['id']})
   token=ok(c.post(url+'/auth/v1/token?grant_type=password',headers={'apikey':pub},json={'email':email,'password':password}))['access_token']
   accounts.append({'id':u['id'],'email':email,'password':password,'Authorization':'Bearer '+token})
  for n in range(2):
   t=post('tenants',{'name':run+str(n),'title':'묻기 검증'});created['tenants'].append(t['id']);save()
   post('memberships',{'tenant_id':t['id'],'user_id':accounts[n]['id'],'role':'보는 사람' if n==0 else '주인'})
  tid=created['tenants'][0];T='재고 점검';today=date.today().isoformat()
  post('object_types',{'tenant_id':tid,'name':T,'kind':'기록'})
  for i,(name,dtype,unit,ent) in enumerate((('품목','text',None,True),('수량','number','개',False))):
   post('property_defs',{'tenant_id':tid,'type_name':T,'name':name,'dtype':dtype,'unit':unit,'is_entity':ent,'position':i})
   post('alias_dict',{'tenant_id':tid,'type_name':T,'alias':name,'prop_name':name})
  stock=(('생수','41'),('라면','13'),('과자','7'))
  ok(sb('POST','/rest/v1/records',json=[encode_record({'tenant_id':tid,'type_name':T,'occurred_at':today,'status':'확정','data':{'품목':n,'수량':q}}) for n,q in stock]))
  # 다른 워크스페이스의 기록은 답과 근거에 섞이면 안 된다.
  post('object_types',{'tenant_id':created['tenants'][1],'name':T,'kind':'기록'})
  ok(sb('POST','/rest/v1/records',json=[encode_record({'tenant_id':created['tenants'][1],'type_name':T,'occurred_at':today,'status':'확정','data':{'품목':'남의 것','수량':'900'}})]))
  headers={'Authorization':accounts[0]['Authorization']};base=f'{a.api}/v1/workspaces/{tid}/ask'
  check('unauthenticated ask denied',c.post(base,json={'question':'q'}).status_code==401)
  check('foreign workspace ask denied',c.post(base,headers={'Authorization':accounts[1]['Authorization']},json={'question':'q'}).status_code==403)
  options=ok(c.get(base,headers=headers))
  check('examples come from confirmed names',options['has_records'] and options['examples'][0]==f'이번 주 {T} 몇 건?',examples=options['examples'])
  started=time.monotonic();r=c.post(base,headers=headers,json={'question':'수량 합계는 몇 개야?'})
  check('viewer gets an answer from the real model',r.status_code==200,status=r.status_code,seconds=round(time.monotonic()-started,1))
  out=r.json();report['answer']={k:out[k] for k in ('text','how','left')};save()
  check('answer uses the code-counted total',str(sum(int(q) for _,q in stock)) in out['text'],text=out['text'])
  check('evidence rows are this workspace only',len(out['evidence'])==3 and {e['품목'] for e in out['evidence']}=={n for n,_ in stock})
  check('how-it-was-found line is shown',any('합계' in h for h in out['how']),how=out['how'])
  logs=ok(sb('GET','/rest/v1/ai_logs',params={'tenant_id':f'eq.{tid}','select':'model,prompt,input_tokens,output_tokens,cost_usd,duration_ms'}))
  report['usage_logged']=bool(logs)
  if logs:check('usage row is recorded',logs[0]['prompt'].startswith('[묻기]') and logs[0]['input_tokens']>0 and float(logs[0]['cost_usd'])>0,log={k:logs[0][k] for k in ('model','input_tokens','output_tokens','cost_usd','duration_ms')})
  from playwright.sync_api import sync_playwright
  with sync_playwright() as pw:
   browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1050})
   page.goto(a.web+'/login');page.locator('input[name=email]').fill(accounts[0]['email']);page.locator('input[name=password]').fill(accounts[0]['password'])
   page.get_by_role('button',name='이메일로 로그인').click();page.locator('.workspace-main h1').wait_for(timeout=60000)
   page.goto(a.web+f'/?workspace={tid}&view=ask');page.get_by_role('button',name=f'이번 주 {T} 몇 건?').click()
   check('example button fills the question',page.get_by_label('질문').input_value()==f'이번 주 {T} 몇 건?')
   page.locator('.ask-form button').click();page.locator('.ask-text').wait_for(timeout=120000)
   check('browser shows answer with evidence count','3' in page.locator('.ask-text').inner_text() and page.get_by_text('근거 기록 3줄').count()==1,text=page.locator('.ask-text').inner_text())
   check('evidence table lists the rows',page.locator('.table-scroll tbody tr').count()==3)
   page.screenshot(path=str(a.output/'ask.png'),full_page=True);browser.close()
  report['status']='passed'
 except Exception as exc:
  report['status']='failed';report['error_type']=type(exc).__name__;save();raise
 finally:
  try:cleanup()
  finally:report['finished_at']=datetime.now(timezone.utc).isoformat();save();c.close()
 print(json.dumps({'status':report['status'],'checks':len(report['checks']),'cleanup':report['cleanup']}))


if __name__=='__main__':main()
