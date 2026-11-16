'use client';
import {useEffect,useRef,useState} from 'react';
type Request=(path:string,init?:RequestInit)=>Promise<any>;
type Job={id:string,status:string,source_input_id:number,model_id?:string,reread_revision?:string,error_code?:string};
type Preview={revision:string,can_reread:boolean,models:string[],default_model:string};
const names:Record<string,string>={'claude-haiku-5-5':'Haiku 5.5','claude-sonnet-5-5':'Sonnet 5.5','claude-opus-5-5':'Opus 5.5'};

export default function Reread({sid,request,onStarted}:{sid:number,request:Request,onStarted:()=>void}){
 const [preview,setPreview]=useState<Preview|null>(null),[model,setModel]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const key=useRef('');
 async function open(){setBusy(true);setError('');try{const p=await request(`sources/${sid}/reread`);setPreview(p);setModel(p.default_model);key.current='';}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function start(){if(!preview)return;setBusy(true);setError('');try{if(!key.current)key.current=crypto.randomUUID();await request(`sources/${sid}/reread`,{method:'POST',body:JSON.stringify({request_key:key.current,expected_revision:preview.revision,model})});setPreview(null);onStarted();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <section aria-label="원본 다시 읽기"><button disabled={busy} onClick={open}>다시 읽기</button>
 {error&&<p role="alert" className="error">{error}</p>}
 {preview&&<div className="panel"><h3>저장된 원본 다시 읽기</h3>{preview.can_reread?<><label>읽는 모델<select aria-label="읽는 모델" disabled={busy} value={model} onChange={e=>{setModel(e.target.value);key.current='';}}>{preview.models.map(m=><option key={m} value={m}>{names[m]||m}</option>)}</select></label><p>선택한 모델로 원본을 새로 읽어요. 성공하면 현재 확인 카드를 새 카드로 바꾸고, 확인이 끝날 때까지 기록은 집계에서 뺍니다. 실패하면 기존 내용을 보존합니다.</p><button className="primary" disabled={busy} onClick={start}>{busy?'요청 중…':'읽기 시작'}</button></>:<p className="info">반영된 기록을 먼저 다시 확인으로 돌려 주세요. 이미 읽는 중이면 끝날 때까지 기다려 주세요.</p>}<button disabled={busy} onClick={()=>setPreview(null)}>닫기</button></div>}
 </section>;
}

export function RereadStatus({tid,onChange,onRunning}:{tid:number,onChange:()=>Promise<void>,onRunning:(v:boolean)=>void}){
 const [jobs,setJobs]=useState<Job[]>([]),[error,setError]=useState('');
 const callback=useRef(onChange);callback.current=onChange;
 const running=useRef(onRunning);running.current=onRunning;
 useEffect(()=>{let live=true,timer:ReturnType<typeof setTimeout>;let signature='';
  async function poll(){try{const r=await fetch(`/api/workspaces/${tid}/documents`);if(!r.ok)throw Error('다시 읽기 상태를 불러오지 못했어요.');const all:Job[]=await r.json();const seen=new Set<number>();const js=all.filter(j=>{if(!j.reread_revision||seen.has(j.source_input_id))return false;seen.add(j.source_input_id);return true;});if(!live)return;setJobs(js);setError('');running.current(js.some(j=>['queued','running'].includes(j.status)));const next=js.map(j=>j.id+j.status).join();if(signature!==next){signature=next;await callback.current();}}catch(e){if(live)setError((e as Error).message);}if(live)timer=setTimeout(poll,4000);}
  poll();return()=>{live=false;clearTimeout(timer);};
 },[tid]);
 return <>{error&&<p className="error" role="alert">{error}</p>}{jobs.filter(j=>j.status!=='canceled').map(j=><div className="panel" role="status" key={j.id}><b>원본 다시 읽기 · {names[j.model_id||'']||j.model_id}</b><p>{j.status==='succeeded'?'새로 읽은 내용을 확인 카드에 표시했어요.':j.status==='failed'?(j.error_code==='source_changed'?'읽는 동안 내용이 바뀌어 교체하지 않았어요. 현재 내용을 확인한 뒤 다시 읽어 주세요.':'다시 읽지 못했어요. 기존 내용은 보존했어요. 올린 종이에서 다시 시도할 수 있어요.'):'원본을 다시 읽고 있어요. 다른 화면으로 가도 계속 진행하며, 완료하면 새 확인 카드가 나타나요.'}</p></div>)}</>;
}
