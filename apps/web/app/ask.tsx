'use client';
import {useEffect,useState} from 'react';
type Request=(path:string,init?:RequestInit)=>Promise<any>;
type Options={models:string[],default_model:string,examples:string[],has_records:boolean};
type Answer={question:string,text:string,how:string[],checked:string|null,left:number,evidence:Record<string,unknown>[]};
const names:Record<string,string>={'claude-haiku-5-5':'빠르게','claude-sonnet-5-5':'보통','claude-opus-5-5':'꼼꼼하게'};
const show=(v:unknown)=>v===null||v===undefined||v===''?'—':typeof v==='object'?JSON.stringify(v):String(v);

export default function Ask({request,go}:{request:Request,go:(view:string)=>void}){
 const [options,setOptions]=useState<Options|null>(null),[question,setQuestion]=useState(''),[model,setModel]=useState('');
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[answer,setAnswer]=useState<Answer|null>(null);
 useEffect(()=>{request('ask').then((o:Options)=>{setOptions(o);setModel(o.default_model);}).catch(e=>setError((e as Error).message));},[request]);
 async function send(e:React.FormEvent){e.preventDefault();const q=question.trim();
  if(!q){setError('질문을 적어 주세요.');return;}
  setBusy(true);setError('');
  try{setAnswer(await request('ask',{method:'POST',body:JSON.stringify({question:q,model})}));}
  catch(err){setError((err as Error).message==='요청을 처리하지 못했어요. 다시 시도해 주세요.'?'답하지 못했어요. 잠시 뒤 다시 눌러 주세요.':(err as Error).message);}
  finally{setBusy(false);}}
 const columns=answer?[...new Set(answer.evidence.flatMap(r=>Object.keys(r)).filter(k=>!k.startsWith('_')))]:[];
 return <><h1>묻기</h1><p className="muted">숫자는 기록에서 세고, 근거 기록을 함께 보여 줘요.</p>
 {error&&<div className="error" role="alert">{error}</div>}
 {options&&!options.has_records?<div className="empty"><h2>아직 확정한 기록이 없어요.</h2><p>종이를 올리고 확인하면 여기서 물어볼 수 있어요.</p><button className="primary" onClick={()=>go('upload')}>올리기</button></div>:<>
 {!!options?.examples.length&&<div className="ask-examples">{options.examples.map(x=><button type="button" key={x} onClick={()=>setQuestion(x)}>{x}</button>)}</div>}
 <form className="ask-form" onSubmit={send}>
  <label>질문<input value={question} onChange={e=>setQuestion(e.target.value)} maxLength={500} placeholder="예: 최근에 기준을 넘은 기록은? / 이번 주 미팅은 누구야?"/></label>
  <label>답하는 방식<select value={model} onChange={e=>setModel(e.target.value)}>{(options?.models||[]).map(m=><option key={m} value={m}>{names[m]||m}</option>)}</select></label>
  <button className="primary" disabled={busy||!options}>묻기</button>
 </form>
 {busy&&<p className="info" role="status">기록을 찾는 중이에요...</p>}
 {answer&&!busy&&<>
  <section className="panel ask-answer">
   <div className="toolbar"><small className="muted">{answer.question}</small>{answer.checked&&<small className="muted">확인한 답</small>}</div>
   {answer.how.map(h=><p className="muted" key={h}>이렇게 찾았어요: {h}</p>)}
   <p className="ask-text">{answer.text}</p>
   {!!answer.left&&<p className="muted">분류 안 된 기록 {answer.left}줄은 세지 않았어요.</p>}
   {answer.checked&&answer.checked.trim()!==answer.text.trim()&&<p className="muted">전에 맞다고 고른 답: {answer.checked}</p>}
  </section>
  <p className="muted">{answer.evidence.length?`근거 기록 ${answer.evidence.length}줄`:'근거로 쓴 기록이 없어요.'}</p>
  {!!answer.evidence.length&&<div className="table-scroll"><table className="plain-table"><thead><tr>{columns.map(c=><th key={c}>{c}</th>)}</tr></thead>
   <tbody>{answer.evidence.map((r,i)=><tr key={String(r._id)+i}>{columns.map(c=><td key={c}>{show(r[c])}</td>)}</tr>)}</tbody></table></div>}
 </>}
 </>}</>;
}
