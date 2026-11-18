'use client';
import {useState} from 'react';
type Request=(path:string,init?:RequestInit)=>Promise<any>;
type Rule={heads:{written:string,means:string}[],head_col:string|null,number_col:string|null,meaning?:string};
type Preview={rule:Rule,understood:{written:string,means:string,into:string}[],rows:number,here:number,before:number,sample:Record<string,string|number>[]};
type Card={id:number,payload:{label:string,written:string,examples?:string[],rows?:number,guess:Rule}};

// 뜻 확인: AI가 짐작한 뜻을 [맞아요]로 받거나, [직접 적기]로 한 줄 설명하면 알아들은 규칙과 바뀌는 줄을 보고 [적용]한다.
export default function MeaningReview({q,request,canReview,onDone,onLater}:{q:Card,request:Request,canReview:boolean,onDone:(note:string)=>void,onLater:()=>void}){
 const p=q.payload,g=p.guess;
 const [writing,setWriting]=useState(false),[said,setSaid]=useState(''),[preview,setPreview]=useState<Preview|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const guessText=g.meaning||[g.head_col&&`${g.head_col} ${g.heads[0]?.means||''}`,g.number_col].filter(Boolean).join(' · ');
 const same=(p.examples||[]).filter(x=>x!==p.written).slice(0,2);
 async function look(){if(!said.trim())return;setBusy(true);setError('');setPreview(null);
  try{setPreview(await request(`meanings/${q.id}/preview`,{method:'POST',body:JSON.stringify({said:said.trim()})}));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function apply(rule:Rule,text:string|null){setBusy(true);setError('');
  try{const r=await request(`meanings/${q.id}/apply`,{method:'POST',body:JSON.stringify({rule,said:text})});onDone(`${r.rows}줄에 뜻을 반영했어요. 다음 사진의 같은 표기는 묻지 않아요.`);}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 const cols=preview?[preview.rule.head_col,preview.rule.number_col].filter(Boolean) as string[]:[];
 return <>
  <h2>{p.label} · {p.written}</h2>
  {!writing?<>
   <p className="muted">이 표기는 이런 뜻인가요?</p>
   <div className="read-value">{guessText}</div>
   <p className="muted meaning-same">같은 모양{same.length?`: ${same.join(', ')} 등`:''} 이 종이에 {p.rows||1}줄</p>
   {canReview?<div className="review-actions"><button className="primary" disabled={busy} onClick={()=>apply(g,null)}>맞아요</button><button disabled={busy} onClick={()=>setWriting(true)}>직접 적기</button><button className="text-button" disabled={busy} onClick={onLater}>나중에</button></div>
    :<p className="info">주인 또는 확인하는 사람이 답할 수 있어요.</p>}
   <p className="hint-known">[맞아요]를 누르면 적힌 글은 그대로 두고 {[g.head_col,g.number_col].filter(Boolean).map(c=>`'${c}'`).join(' · ')} 칸에 뜻을 넣어요.</p>
  </>:<>
   <label>이 표기의 뜻을 한 줄로 알려 주세요<input aria-label="표기의 뜻" value={said} maxLength={300} placeholder="예: 현수막, 700폭. '현'만 써도 현수막이에요" onChange={e=>{setSaid(e.target.value);setPreview(null);}} onBlur={look} onKeyDown={e=>{if(e.key==='Enter'){e.preventDefault();look();}}}/></label>
   {!preview&&<p className="muted">다 적고 Enter를 누르면 알아들은 내용이 보여요.</p>}
   {busy&&!preview&&<p role="status" className="muted">알아듣는 중이에요…</p>}
   {preview&&<div className="meaning-preview">
    <b>이렇게 알아들었어요</b>
    <table className="plain-table"><thead><tr><th>적힌 것</th><th>뜻</th><th>들어갈 곳</th></tr></thead><tbody>{preview.understood.map((u,i)=><tr key={i}><td>{u.written}</td><td>{u.means}</td><td>{u.into}</td></tr>)}</tbody></table>
    <b>적용하면 바뀌는 줄 {preview.rows}줄</b> <span className="muted">(이 종이 {preview.here} · 지난 종이 {preview.before})</span>
    {!!preview.sample.length&&<table className="plain-table"><thead><tr><th>적힌 그대로</th>{cols.map(c=><th key={c}>{c}</th>)}</tr></thead><tbody>{preview.sample.map((s,i)=><tr key={i}><td>{s.written}</td>{cols.map(c=><td key={c}>{s[c]??''}</td>)}</tr>)}</tbody></table>}
    <p className="muted">켜 둔 자동화 · 올린 지표는 바뀌지 않아요. 숫자는 적힌 글에 있는 것만 넣어요.</p>
   </div>}
   {canReview&&<div className="review-actions"><button className="primary" disabled={busy||!preview||!preview.rows} onClick={()=>preview&&apply(preview.rule,said.trim())}>적용</button><button className="text-button" disabled={busy} onClick={onLater}>나중에</button></div>}
  </>}
  {error&&<p className="error" role="alert">{error}</p>}
 </>;
}
