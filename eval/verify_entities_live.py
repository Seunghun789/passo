"""Opt-in real Auth/API/worker/UI check of 대상 등록 · 대상 화면 · 지식그래프 with one real paper read and verified cleanup."""
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
 c=httpx.Client(timeout=120,trust_env=False);run='passo-entities-probe-'+uuid.uuid4().hex
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
  failures=[];objects=[]
  for tid in created['tenants']:  # 이 검증이 올린 원본 사진도 지운다
   objects+=[r['storage_path'] for r in ok(sb('GET','/rest/v1/source_inputs',params={'tenant_id':f'eq.{tid}','select':'storage_path'})) if r.get('storage_path')]
  if objects and not sb('DELETE','/storage/v1/object/passo-originals',json={'prefixes':objects}).is_success:failures.append('storage_delete')
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
   t=post('tenants',{'name':run+str(n),'title':'대상 검증'});created['tenants'].append(t['id']);save()
  post('memberships',{'tenant_id':created['tenants'][0],'user_id':accounts[0]['id'],'role':'주인'})
  post('memberships',{'tenant_id':created['tenants'][0],'user_id':accounts[1]['id'],'role':'보는 사람'})
  post('memberships',{'tenant_id':created['tenants'][1],'user_id':accounts[2]['id'],'role':'주인'})
  tid=created['tenants'][0];photo=ROOT/'dummy/samples/retail-inventory/photos/2026-10-12.jpg';content=photo.read_bytes()
  owner,viewer,other=({'Authorization':x['Authorization']} for x in accounts);base=f'{a.api}/v1/workspaces/{tid}'
  started=time.monotonic()
  job=ok(c.post(base+'/documents',headers={**owner,'Content-Type':'image/jpeg','Idempotency-Key':str(uuid.uuid4())},params={'filename':photo.name},content=content))
  def ready():
   d=ok(c.get(base+'/documents/'+job['id'],headers=owner))
   if d['job']['status']=='failed':raise RuntimeError('worker failed')
   return d if d['job']['status']=='succeeded' else None
  end=time.monotonic()+600
  while not (d:=ready()):
   if time.monotonic()>end:raise TimeoutError('worker')
   time.sleep(3)
  check('worker reads the paper',len(d['records'])>=3,rows=len(d['records']),seconds=round(time.monotonic()-started,1))
  logs=ok(sb('GET','/rest/v1/ai_logs',params={'tenant_id':f'eq.{tid}','prompt':'like.[워커*','select':'prompt,model,input_tokens,cost_usd'}))
  check('worker AI calls are recorded',any(l['prompt'].startswith('[워커 읽기]') for l in logs) and any(l['prompt'].startswith('[워커 구조]') for l in logs),
   calls=[l['prompt'].split(']')[0]+']' for l in logs],cost=round(sum(float(l['cost_usd']) for l in logs),4))
  classes=ok(sb('GET','/rest/v1/object_types',params={'tenant_id':f'eq.{tid}','kind':'eq.대상','select':'name'}))
  refs=ok(sb('GET','/rest/v1/property_defs',params={'tenant_id':f'eq.{tid}','ref_class':'not.is.null','select':'type_name,name,ref_class'}))
  ents=ok(sb('GET','/rest/v1/entities',params={'tenant_id':f'eq.{tid}','select':'id,class_name,name'}))
  check('entity class registered right after reading',len(classes)>=1 and len(refs)>=1,classes=[x['name'] for x in classes],refs=refs)
  check('entities registered from the paper',len(ents)>=3,entities=[e['name'] for e in ents][:10])
  trail=ok(sb('GET','/rest/v1/proposals',params={'tenant_id':f'eq.{tid}','kind':'in.(대상 분류,대상)','select':'kind,status,evidence'}))
  check('entity work leaves approved cards with reasons',trail and all(q['status']=='승인' for q in trail),kinds=[q['kind'] for q in trail])
  check('foreign workspace cannot see entities',c.get(base+'/entities',headers=other).status_code==403)
  table=ok(c.get(base+'/entities',headers=viewer))
  check('viewer sees the entity table',table['can_edit'] is False and table['classes'][0]['total']==len([e for e in ents if e['class_name']==table['classes'][0]['name']]))
  check('viewer cannot register entities',c.post(base+'/entities/recommend',headers=viewer).status_code==403)
  # 이름 안에 띄어쓰기가 있는 대상을 띄어쓰기 없이 다시 적는다(예: '생수 500ml' → '생수500ml')
  ref,first=next((r,e['name']) for r in refs for e in ents if e['class_name']==r['ref_class'] and ' ' in e['name'])
  T=ref['type_name'];C=ref['ref_class'];spaced=first.replace(' ','')
  ok(c.post(base+'/manual-records',headers=owner,json={'request_key':str(uuid.uuid4()),'type_name':T,'occurred_at':date.today().isoformat(),'data':{ref['name']:spaced}}))
  rec=ok(c.post(base+'/entities/recommend',headers=owner))
  aliases=ok(sb('GET','/rest/v1/entity_aliases',params={'tenant_id':f'eq.{tid}','alias':f'eq.{spaced.strip()}','select':'entity_id'}))
  check('differently spaced name becomes an alias without AI',rec['same']>=1 and len(aliases)==1,result=rec,written=spaced)
  g=ok(c.get(base+'/graph',headers=owner))
  check('graph shows the record type and the entity class',{f'T:{T}',f'C:{C}'}<= {n['id'] for n in g['nodes']})
  nums=[r for r in g['refs'] if r.startswith(T+'.') and r!=f"{T}.{ref['name']}"]
  pick=ok(c.post(base+'/links',headers=owner,json={'from_ref':f"{T}.{ref['name']}",'to_ref':nums[0],'kind':'연결'}))
  g=ok(c.get(base+'/graph',headers=owner));p=next(x for x in g['pending'] if x['id']==pick['id'])
  check('user link becomes a dashed card with counted evidence',p['counted'] and any(e.get('dashes') is True for e in g['edges']),counted=p['counted'])
  check('viewer cannot propose links',c.post(base+'/links',headers=viewer,json={'from_ref':f"{T}.{ref['name']}",'to_ref':nums[0],'kind':'연결'}).status_code==403)
  ok(c.post(base+f'/reviews/{p["id"]}',headers=owner,json={'expected_payload':p['payload'],'answer':'accept'}))
  g=ok(c.get(base+'/graph',headers=owner))
  check('[맞아요] turns it into a confirmed link',len(g['links'])>=1 and not any(x['id']==p['id'] for x in g['pending']),links=[l['text'] for l in g['links']])
  # 직접 고친 것: 카드로 올라가고 [적용] 때만 반영된다
  q=ok(c.post(base+'/edits',headers=owner,json={'kind':'대상 속성','payload':{'class':C,'attr':'단가','dtype':'number'}}))['id']
  check('edit waits as a card until applied',not any(a=='단가' for a in ok(c.get(base+'/entities',headers=owner))['classes'][[x['name'] for x in table['classes']].index(C)]['attrs'])
   and any(x['id']==q for x in ok(c.get(base+'/entities',headers=owner))['cards']))
  check('viewer cannot apply an edit card',c.post(base+f'/edits/{q}',headers=viewer,json={'ok':True}).status_code==403)
  ok(c.post(base+f'/edits/{q}',headers=owner,json={'ok':True}))
  ents2=ok(c.get(base+'/entities',headers=owner));cls=next(x for x in ents2['classes'] if x['name']==C)
  check('[적용] adds the attribute to the class table',cls['attrs']==['단가'])
  check('bad edit is explained',c.post(base+'/edits',headers=owner,json={'kind':'속성 값','payload':{'entity_id':cls['rows'][0]['id'],'attr':'없는 정보','new':1}}).json().get('detail','').startswith('그 분류에 없는 정보'))
  q2=ok(c.post(base+'/edits',headers=owner,json={'kind':'속성 값','payload':{'entity_id':cls['rows'][0]['id'],'attr':'단가','new':1200}}))['id']
  ok(c.post(base+f'/edits/{q2}',headers=owner,json={'ok':True}))
  cls=next(x for x in ok(c.get(base+'/entities',headers=owner))['classes'] if x['name']==C)
  check('attribute value applied',cls['rows'][0]['attrs']['단가']==1200)
  q3=ok(c.post(base+'/edits',headers=owner,json={'kind':'칸 설정','payload':{'type':T,'op':'단위·설명','prop':nums[0].split('.',1)[1],'unit':'개','description':'직접 단 설명'}}))['id']
  ok(c.post(base+f'/edits/{q3}',headers=owner,json={'ok':True}))
  g=ok(c.get(base+'/graph',headers=owner))
  check('unit and description applied to the column',next(x for x in g['props'][T] if x['name']==nums[0].split('.',1)[1])['description']=='직접 단 설명')
  check('applied edits are listed for undo',len(ok(c.get(base+'/entities',headers=owner))['undoable'])>=2)
  from playwright.sync_api import sync_playwright
  with sync_playwright() as pw:
   browser=pw.chromium.launch();page=browser.new_page(viewport={'width':1440,'height':1050})
   page.goto(a.web+'/login');page.locator('input[name=email]').fill(accounts[0]['email']);page.locator('input[name=password]').fill(accounts[0]['password'])
   page.get_by_role('button',name='이메일로 로그인').click();page.locator('.workspace-main h1').wait_for(timeout=60000)
   page.goto(a.web+f'/?workspace={tid}&view=entities');page.locator('.entity-table tbody tr').first.wait_for(timeout=60000)
   page.get_by_role('tab',name=C).click()
   page.get_by_text(spaced,exact=False).first.wait_for(timeout=10000)
   page.screenshot(path=str(a.output/'entities.png'),full_page=True)
   want=len([e for e in ents if e['class_name']==C])
   check('browser entity tab lists entities with aliases',page.locator('.entity-table tbody tr').count()==want,rows=page.locator('.entity-table tbody tr').count(),want=want)
   page.goto(a.web+f'/?workspace={tid}&view=graph');page.locator('.graph canvas').wait_for(timeout=60000)
   page.get_by_label('점 고르기').select_option(f'C:{C}');page.locator('.node-card').wait_for(timeout=10000)
   check('browser graph draws and opens a node card',page.locator('.graph canvas').count()==1 and C in page.locator('.node-card').inner_text())
   page.screenshot(path=str(a.output/'graph.png'),full_page=True);browser.close()
  report['status']='passed'
 except Exception as exc:
  report['status']='failed';report['error_type']=type(exc).__name__;save();raise
 finally:
  try:cleanup()
  finally:report['finished_at']=datetime.now(timezone.utc).isoformat();save();c.close()
 print(json.dumps({'status':report['status'],'checks':len(report['checks']),'cleanup':report['cleanup']}))


if __name__=='__main__':main()
