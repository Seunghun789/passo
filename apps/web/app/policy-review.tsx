'use client';
import {useEffect,useState} from 'react';
type Request=(path:string,init?:RequestInit)=>Promise<any>;
type Preview={revision:string,can_reopen:boolean,records:{id:number,type_name:string,status:string,data:Record<string,unknown>}[]};
const show=(v:any):string=>v&&typeof v==='object'?('raw' in v?String(v.raw??'—'):JSON.stringify(v)):String(v??'—');
export function ReadReview({qid,sid,request,canReview,onDone}:{qid:number,sid:number,request:Request,canReview:boolean,onDone:()=>Promise<void>}){
 const [preview,setPreview]=useState<Preview|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[reload,setReload]=useState(0);
 useEffect(()=>{let live=true;setError('');setPreview(null);request(`sources/${sid}/review`).then(s=>{if(live)setPreview(s);}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[sid,request,reload]);
 async function answer(answer:string){if(!preview)return;setBusy(true);try{await request(`reviews/${qid}/read`,{method:'POST',body:JSON.stringify({expected_revision:preview.revision,answer})});await onDone();}catch(e){setError((e as Error).message);setPreview(null);}finally{setBusy(false);}}
 return <section aria-label="문서 다시 확인"><h3>기록 다시 확인</h3>{error&&<p className="error" role="alert">{error}</p>}{!preview?<button disabled={busy} onClick={()=>setReload(n=>n+1)}>현재 내용 다시 불러오기</button>:<><p>확정하면 집계에 다시 포함합니다. 원본과 미확정 셀 상태는 그대로 보존합니다.</p><div className="table-scroll"><table><thead><tr><th>기록</th><th>현재 값</th><th>상태</th></tr></thead><tbody>{preview.records.map(r=><tr key={r.id}><td>{r.type_name} #{r.id}</td><td>{Object.entries(r.data).map(([k,v])=><div key={k}>{k}: {show(v)}</div>)}</td><td>{r.status}</td></tr>)}</tbody></table></div>{canReview&&<div className="review-actions"><button disabled={busy} className="primary" onClick={()=>answer('accept')}>내용 확인 후 확정</button><button disabled={busy} onClick={()=>answer('reject')}>이 기록 제외</button></div>}</>}</section>;
}
