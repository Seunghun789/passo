"""Run separately: python -m backend.worker. PostgreSQL leases survive process death."""
import argparse
import hashlib
import json
import os
import signal
import threading
import time

import httpx


class Worker:
    def __init__(self):
        self.url = os.environ['SUPABASE_URL'].rstrip('/')
        key = os.environ['SUPABASE_WORKER_SECRET_KEY']
        self.client = httpx.Client(timeout=45,trust_env=False,headers={'apikey':key,'Authorization':'Bearer '+key})

    def request(self, method, path, **kw):
        r = self.client.request(method,self.url+path,**kw)
        if not r.is_success:
            raise RuntimeError('worker_gateway_'+str(r.status_code))
        return r

    def rpc(self, name, body=None):
        return self.request('POST','/rest/v1/rpc/'+name,json=body or {}).json()

    def process(self, job):
        from backend.extraction import run_ocr, run_model, run_structure, run_entities, make_payload
        stop, lost = threading.Event(), threading.Event()
        args = {'jid':job['id'],'fence':job['lease_token']}
        def heartbeat():
            while not stop.wait(25):
                try:
                    if not self.rpc('passo_worker_save',args):
                        lost.set(); return
                except Exception:
                    lost.set(); return
        thread = threading.Thread(target=heartbeat,daemon=True);thread.start()
        def save(state):
            if lost.is_set() or not self.rpc('passo_worker_save',{**args,'checkpoint':state}):
                raise RuntimeError('lease_lost')
        try:
            source = self.request('GET','/rest/v1/source_inputs',params={'id':f"eq.{job['source_input_id']}",
                'tenant_id':f"eq.{job['tenant_id']}",'select':'storage_path'}).json()[0]
            bucket = job.get('original_bucket', 'passo-originals')
            content = self.request('GET','/storage/v1/object/authenticated/'+bucket+'/'+source['storage_path']).content
            if hashlib.sha256(content).hexdigest()!=job['sha256'] or len(content)!=job['byte_size']:
                raise ValueError('original_hash_mismatch')
            from backend.documents import validate_document
            validate_document(content,job['media_type'])
            rows = self.request('GET','/rest/v1/passo_checkpoints',params={'job_id':f"eq.{job['id']}",
                'tenant_id':f"eq.{job['tenant_id']}",'order':'revision.desc','limit':1,'select':'state'}).json()
            state = rows[0]['state'] if rows else {}
            if 'ocr' not in state:
                state['ocr'] = run_ocr(content,job['media_type']);save(state)
            if 'extraction' not in state:
                state['extraction'] = run_model(content,job['media_type'],job.get('model_id'));save(state)
            payload = make_payload(state['extraction']['sheet'],state['ocr'])
            fetch = lambda table,params: self.request('GET','/rest/v1/'+table,params=params).json()
            if 'structure' not in state:
                state['structure'] = run_structure(fetch,job['tenant_id'],state['extraction']['sheet'],
                                                   payload['records'],job.get('model_id'));save(state)
            from backend.structure import apply_splits
            apply_splits(payload,state['structure'].get('splits'))
            payload['structure'] = {k:state['structure'][k] for k in ('type','title','props','links','samples','evidence')}
            if 'entities' not in state:
                state['entities'] = run_entities(fetch,job['tenant_id'],payload['structure'],payload['records']);save(state)
            payload['entities'] = {k:state['entities'][k] for k in ('classes','entities','same')}
            for record in payload['records']:
                record['type_name'] = payload['structure']['type']
            if lost.is_set() or not self.rpc('passo_worker_finish',{**args,'payload':payload}):
                raise RuntimeError('lease_lost')
            print(json.dumps({'job':job['id'],'status':'published','records':len(payload['records'])}),flush=True)
            self.log_usage(job,state)
        except Exception as exc:
            # No model output, document content, credentials or transport exceptions in logs.
            print(json.dumps({'job':job['id'],'error_type':type(exc).__name__}),flush=True)
            self.rpc('passo_worker_fail',args)
        finally:
            stop.set();thread.join(timeout=50)

    def log_usage(self, job, state):
        """이 종이를 읽으며 부른 AI(읽기 · 구조 · 대상)를 ai_logs 에 남긴다. 종이 내용과 답은 남기지 않는다.
        남기지 못해도 이미 반영한 종이는 그대로다."""
        from core.llm import PRICE
        steps = [('읽기',[state.get('extraction',{}).get('usage') or {}]),('구조',state.get('structure',{}).get('usage') or []),
                 ('대상',state.get('entities',{}).get('usage') or [])]
        rows = []
        for step,usages in steps:
            for u in usages:
                if u.get('model') not in PRICE:
                    continue
                price = PRICE[u['model']]
                rows.append({'tenant_id':job['tenant_id'],'model':u['model'],'prompt':f'[워커 {step}] 종이 {job["source_input_id"]}','answer':'',
                             'input_tokens':int(u.get('input_tokens') or 0),'output_tokens':int(u.get('output_tokens') or 0),
                             'cost_usd':round((int(u.get('input_tokens') or 0)*price[0]+int(u.get('output_tokens') or 0)*price[1])/1_000_000,6),
                             'duration_ms':round(u['seconds']*1000) if u.get('seconds') is not None else None})  # 한 번에 넣는 줄은 칸이 같아야 한다
        if not rows:
            return
        try:
            self.request('POST','/rest/v1/ai_logs',json=rows,headers={'Prefer':'return=minimal'})
        except Exception:
            print(json.dumps({'job':job['id'],'usage':'log_failed'}),flush=True)

    def close(self):
        self.client.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
    stop=threading.Event()
    for sig in (signal.SIGTERM,signal.SIGINT):
        signal.signal(sig,lambda *_:stop.set())
    w=Worker()
    try:
        while not stop.is_set():
            jobs=w.rpc('passo_claim_document')
            if jobs: w.process(jobs[0])
            if args.once: break
            if not jobs: stop.wait(3)
    finally: w.close()

if __name__=='__main__':main()
