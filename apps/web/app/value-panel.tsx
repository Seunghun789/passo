'use client';
import {useCallback,useEffect,useState} from 'react';
type Request=(path:string,init?:RequestInit)=>Promise<any>;
type Info={type:string,label:string,prop:string|null,dtype:string|null,class:string|null,can_edit:boolean,
 entity:{class:string,name:string,records:number,aliases:string[],attrs:Record<string,unknown>}|null,
 similar:{name:string,records:number}[],row:{label:string,class:string,name:string,known:boolean,linked:boolean}[]};
type Card={id:number,kind:string,text:string,impact:string[]};

// "이 값": 기록 표 · 확인 카드의 값이 가리키는 대상, 같은 줄의 다른 대상과 [이어 보기], 다르게 적힌 값의 [같은 대상] · [등록],
// 대상 칸이 아니면 "이 칸은 무엇을 가리키나요?". 바꾸는 것은 모두 카드로 올라가 [적용]을 눌러야 반영된다.
export default function ValuePanel({request,type,label,value,rid,go,onChanged}:{request:Request,type:string,label:string,value:string,rid?:number|null,go?:(v:string)=>void,onChanged?:()=>void}){
 const [info,setInfo]=useState<Info|null>(null),[card,setCard]=useState<Card|null>(null),[cls,setCls]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const load=useCallback(()=>{const q=new URLSearchParams({type_name:type,label,value:value||''});if(rid)q.set('rid',String(rid));
  return request(`value?${q}`).then(setInfo).catch(()=>setInfo(null));},[request,type,label,value,rid]);
 useEffect(()=>{setCard(null);setNotice('');setError('');setCls('');load();},[load]);
 async function post(kind:string,payload:object){setBusy(true);setError('');setNotice('');
  try{setCard(await request('edits',{method:'POST',body:JSON.stringify({kind,payload})}));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function answer(ok:boolean){if(!card)return;setBusy(true);setError('');
  try{await request(`edits/${card.id}`,{method:'POST',body:JSON.stringify({ok})});setCard(null);setNotice(ok?'반영했어요.':'반영하지 않았어요.');await load();onChanged?.();}
  catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function link(to:string){setBusy(true);setError('');setNotice('');
  try{await request('links',{method:'POST',body:JSON.stringify({from_ref:info?.class,to_ref:to,kind:'연결'})});setNotice('"관계 제안" 카드로 올렸어요. 확인에서 [맞아요]를 누르면 이어져요.');}
  catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 if(!info||!info.prop)return null;
 const edit=info.can_edit,v=String(value||'').trim();
 const preview=card&&<div className="value-card"><b>{card.text}</b>
  {card.impact.length?<ul className="impact">{card.impact.map(x=><li key={x}>{x}</li>)}</ul>:<p className="muted">켜 둔 자동화 · 올린 지표는 그대로예요.</p>}
  <div className="row-actions"><button className="primary" disabled={busy} onClick={()=>answer(true)}>적용</button><button className="text-button" disabled={busy} onClick={()=>{setCard(null);setNotice('카드는 대상 화면의 "직접 고친 것"에 남아 있어요.');}}>나중에</button></div></div>;
 return <section className="value-panel" aria-label="이 값">
  {info.class&&info.entity&&<><b className="value-title">이 값</b><div className="value-entity">{info.entity.class} · {info.entity.name}</div>
   <p className="muted value-meta">기록 {info.entity.records}줄{info.entity.aliases.length?` · 별칭 ${info.entity.aliases.join(', ')}`:''}{Object.keys(info.entity.attrs).length?` · ${Object.entries(info.entity.attrs).slice(0,3).map(([k,x])=>`${k} ${String(x)}`).join(' · ')}`:''}</p>
   {go&&<div className="row-actions"><button onClick={()=>go('entities')}>대상에서 보기</button></div>}</>}
  {info.class&&!info.entity&&v&&<><b className="value-title">이 값</b><div className="value-entity">{info.class}에 없는 이름이에요</div>
   {info.similar.length?<p className="muted value-meta">확정한 {info.class} 중 비슷한 것</p>:null}
   {info.similar.map(s=><div className="row-actions" key={s.name}><span>{s.name} <span className="muted">기록 {s.records}줄</span></span>{edit&&!card&&<button disabled={busy} onClick={()=>post('같은 대상',{class:info.class,same_as:s.name,value:v})}>같은 대상</button>}</div>)}
   {edit&&!card&&<div className="row-actions"><span className="muted">새 {info.class}(이)면</span><button disabled={busy} onClick={()=>post('대상',{class:info.class,values:[v]})}>등록</button></div>}</>}
  {!info.class&&(info.dtype==='text'||info.dtype==='choice')&&edit&&<><b className="value-title">이 칸은 무엇을 가리키나요?</b>
   <p className="muted value-meta">'{info.prop}' 칸은 아직 대상 칸이 아니에요. 분류 이름을 적으면 이 칸의 값들이 그 분류의 대상이 돼요.</p>
   {!card&&<label className="value-class">분류 이름<input value={cls} maxLength={100} placeholder="예: 품목, 거래처" onChange={e=>setCls(e.target.value)}
    onKeyDown={e=>{if(e.key==='Enter'&&cls.trim()){e.preventDefault();post('칸 설정',{type:info.type,op:'대상 칸',prop:info.prop,class:cls.trim()});}}}/></label>}
   {!card&&<p className="muted value-meta">다 적고 Enter를 누르면 바뀌는 것이 카드로 보여요.</p>}</>}
  {preview}
  {info.class&&info.row.length>0&&<div className="value-row"><b>같은 줄의 다른 대상</b>{info.row.map(r=><div className="row-actions" key={r.label}>
   <span>{r.class} · {r.name}</span>{r.linked?<span className="muted">이어져 있어요</span>:<><span className="muted">{info.class}와(과) {r.class}는 아직 이어지지 않았어요</span>{edit&&<button disabled={busy} onClick={()=>link(r.class)}>이어 보기</button>}</>}</div>)}</div>}
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="success" role="status">{notice}</p>}
 </section>;
}
