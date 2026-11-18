'use client';
import {useState} from 'react';
type Request=(path:string,init?:RequestInit)=>Promise<any>;
type Src={id:number,name:string,auto:boolean,created_at:string};
const DAY=86400000;
export const recentAuto=(s:Src)=>s.auto&&Date.now()-Date.parse(s.created_at)<7*DAY;

// 올린 종이의 [되돌리기]: AI가 바로 반영한 7일 안의 종이를 다시 확인 중으로 돌린다. 칸 · 대상 · 관계는 그대로다
export default function UndoPaper({source,request,onDone}:{source:Src,request:Request,onDone:()=>Promise<void>}){
 const [preview,setPreview]=useState<{revision:string,records:unknown[]}|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const left=Math.max(1,7-Math.floor((Date.now()-Date.parse(source.created_at))/DAY));
 async function ask(){setBusy(true);setError('');try{setPreview(await request(`sources/${source.id}/review`));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function apply(){if(!preview)return;setBusy(true);setError('');
  try{await request(`sources/${source.id}/reopen`,{method:'POST',body:JSON.stringify({expected_revision:preview.revision})});setPreview(null);await onDone();}
  catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <><span className="chip done">AI가 바로 반영 · {left}일 남음</span><button disabled={busy} onClick={ask}>되돌리기</button>
  {preview&&<div className="undo-confirm" role="dialog"><b>{source.name}를 되돌릴까요?</b>
   <p>기록 {preview.records.length}줄이 다시 확인 중으로 돌아가 표 · 지표 · 묻기에서 빠져요. 칸 · 대상 · 관계는 그대로예요.</p>
   <div className="row-actions"><button disabled={busy} onClick={()=>setPreview(null)}>아니요</button><button className="primary" disabled={busy} onClick={apply}>적용</button></div></div>}
  {error&&<p className="error" role="alert">{error}</p>}</>;
}
