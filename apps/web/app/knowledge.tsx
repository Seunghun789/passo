'use client';
import {useCallback,useEffect,useRef,useState} from 'react';
type Request=(path:string,init?:RequestInit)=>Promise<any>;
type EntityRow={id:number,name:string,aliases:string[],attrs:Record<string,unknown>,records:number};
type EntityClass={name:string,parent:string|null,attrs:string[],total:number,rows:EntityRow[],children:string[],pointed_by:string[]};
type Info={name:string,kind:string,desc:string,stats:[string,string][],rels:string[],count:number};
type GraphNode={id:string,label:string,info:Info,[k:string]:unknown};
type GraphEdge={from:string,to:string,[k:string]:unknown};
type Pending={id:number,payload:Record<string,unknown>,text:string,reason?:string,counted?:string};
type Card={id:number,kind:string,text:string,impact:string[]};
type ClassLink={id:number,from:string,to:string,name:string,attrs:string[],pairs:{from:string,to:string,values:Record<string,unknown>}[]};
type Graph={can_edit:boolean,has_records:boolean,nodes:GraphNode[],edges:GraphEdge[],links:{id:number,text:string}[],pending:Pending[],refs:string[],kinds:string[],
 cards:Card[],props:Record<string,{name:string,dtype:string,unit:string|null,description:string|null}[]>,members:Record<string,string[]>,class_attrs:Record<string,string[]>};
const DTYPES:[string,string][]=[['text','글'],['number','숫자'],['date','날짜'],['choice','고르는 값']];
type Post=(kind:string,payload:object)=>Promise<boolean>;

function useEdits(request:Request,reload:()=>Promise<unknown>){
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const post:Post=async(kind,payload)=>{setBusy(true);setError('');setNotice('');
  try{await request('edits',{method:'POST',body:JSON.stringify({kind,payload})});await reload();setNotice('카드로 올렸어요. 카드에서 [적용]을 눌러야 반영돼요.');return true;}
  catch(e){setError(fail(e));return false;}finally{setBusy(false);}};
 const answer=async(id:number,ok:boolean)=>{setBusy(true);setError('');setNotice('');
  try{await request(`edits/${id}`,{method:'POST',body:JSON.stringify({ok})});await reload();setNotice(ok?'반영했어요.':'반영하지 않았어요.');}
  catch(e){setError(fail(e));}finally{setBusy(false);}};
 return {busy,error,notice,post,answer};
}

function EditCards({cards,busy,answer}:{cards:Card[],busy:boolean,answer:(id:number,ok:boolean)=>void}){
 if(!cards.length)return null;
 return <section className="edit-cards"><h2>직접 고친 것 {cards.length}개</h2>{cards.map(c=><article className="panel suggestion" key={c.id}>
  <div className="alert-head"><span className="tag">{c.kind}</span><b>{c.text}</b></div>
  {c.impact.length?<ul className="impact">{c.impact.map(x=><li key={x}>{x}</li>)}</ul>:<p className="muted">켜 둔 자동화 · 올린 지표는 그대로예요.</p>}
  <div className="card-actions"><button disabled={busy} onClick={()=>answer(c.id,false)}>아니요</button><button className="primary" disabled={busy} onClick={()=>answer(c.id,true)}>적용</button></div></article>)}</section>;
}

function ClassTools({cls,members,busy,post}:{cls:string,members:string[],busy:boolean,post:Post}){
 const [task,setTask]=useState('정보'),[a,setA]=useState(''),[b,setB]=useState('text'),[picked,setPicked]=useState<string[]>([]);
 const go=async(kind:string,payload:object)=>{if(await post(kind,payload)){setA('');setPicked([]);}};
 return <div className="class-tools"><div className="segments">{['정보','별칭','묶기','상위 분류'].map(t=><button key={t} aria-pressed={task===t} onClick={()=>{setTask(t);setA('');}}>{t}</button>)}</div>
  {task==='정보'&&<div className="pick-form"><label>새 정보 이름<input value={a} maxLength={100} onChange={e=>setA(e.target.value)} placeholder="예: 단가, 설치일"/></label>
   <label>값 종류<select value={b} onChange={e=>setB(e.target.value)}>{DTYPES.map(([k,l])=><option key={k} value={k}>{l}</option>)}</select></label>
   <button className="primary" disabled={busy||!a.trim()} onClick={()=>go('대상 속성',{class:cls,attr:a,dtype:b})}>정보 더하기</button></div>}
  {task==='별칭'&&<div className="pick-form"><label>대상<select value={picked[0]||''} onChange={e=>setPicked([e.target.value])}><option value="">고르세요</option>{members.map(m=><option key={m}>{m}</option>)}</select></label>
   <label>별칭<input value={a} maxLength={200} onChange={e=>setA(e.target.value)} placeholder="예: P-03"/></label>
   <button className="primary" disabled={busy||!a.trim()||!picked[0]} onClick={()=>go('같은 대상',{class:cls,same_as:picked[0],value:a})}>별칭 더하기</button></div>}
  {task==='묶기'&&<><div className="pick-form"><label>하위 분류 이름<input value={a} maxLength={100} onChange={e=>setA(e.target.value)} placeholder="예: 식품"/></label></div>
   <div className="member-picks">{members.map(m=><label key={m}><input type="checkbox" checked={picked.includes(m)} onChange={e=>setPicked(e.target.checked?[...picked,m]:picked.filter(x=>x!==m))}/>{m}</label>)}</div>
   <button className="primary" disabled={busy||!a.trim()||!picked.length} onClick={()=>go('상위 분류',{class:a,parent:cls,members:picked})}>하위 분류로 묶기</button></>}
  {task==='상위 분류'&&<div className="pick-form"><label>상위 분류 이름<input value={a} maxLength={100} onChange={e=>setA(e.target.value)} placeholder="예: 자산"/></label>
   <button className="primary" disabled={busy||!a.trim()} onClick={()=>go('상위 분류',{class:cls,parent:a,members:[]})}>상위 분류 정하기</button></div>}
 </div>;
}

function LinkAttrs({link,busy,post}:{link:ClassLink,busy:boolean,post:Post}){
 const [attr,setAttr]=useState(''),[dtype,setDtype]=useState('number'),[vals,setVals]=useState<Record<string,string>>({});
 return <article className="panel link-attrs"><b>{link.from} — {link.to} ({link.name})</b>
  <div className="pick-form"><label>관계 정보 이름<input value={attr} maxLength={100} onChange={e=>setAttr(e.target.value)} placeholder="예: 단가"/></label>
   <label>값 종류<select value={dtype} onChange={e=>setDtype(e.target.value)}>{DTYPES.map(([k,l])=><option key={k} value={k}>{l}</option>)}</select></label></div>
  {link.pairs.length?<div className="table-wrap"><table className="plain-table"><thead><tr><th>{link.from}</th><th>{link.to}</th>{link.attrs.map(x=><th key={x}>{x}</th>)}<th>값</th></tr></thead>
   <tbody>{link.pairs.map(p=>{const k=`${p.from}|${p.to}`;return <tr key={k}><td>{p.from}</td><td>{p.to}</td>{link.attrs.map(x=><td key={x}>{show(p.values[x])}</td>)}
    <td><input aria-label={`${p.from} ${p.to} 값`} value={vals[k]||''} onChange={e=>setVals({...vals,[k]:e.target.value})}/></td></tr>;})}</tbody></table></div>:<p className="muted">기록에 함께 나온 대상 쌍이 아직 없어요.</p>}
  <button className="primary" disabled={busy||!attr.trim()||!Object.values(vals).some(v=>v.trim())} onClick={async()=>{if(await post('관계 속성',{link_id:link.id,attr,dtype,values:Object.fromEntries(Object.entries(vals).filter(([,v])=>v.trim()).map(([k,v])=>[k,dtype==='number'&&Number.isFinite(Number(v))?Number(v):v]))})){setAttr('');setVals({});}}}>관계 정보 올리기</button>
 </article>;
}

const show=(v:unknown)=>v===null||v===undefined||v===''?'—':typeof v==='object'?JSON.stringify(v):String(v);
const fail=(e:unknown)=>{const m=(e as Error).message;return m==='요청을 처리하지 못했어요. 다시 시도해 주세요.'?'잠시 뒤 다시 눌러 주세요.':m;};
const refText=(r:string)=>{const i=r.indexOf('.');return i<0?r:`${r.slice(i+1)}(${r.slice(0,i)})`;};

export function Entities({request,go}:{request:Request,go:(v:string)=>void}){
 const [data,setData]=useState<{can_edit:boolean,has_records:boolean,classes:EntityClass[],links:ClassLink[],cards:Card[],undoable:{id:number,kind:string,text:string}[]}|null>(null),[tab,setTab]=useState(''),[q,setQ]=useState('');
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[changed,setChanged]=useState<Record<string,string>>({});
 const load=useCallback(()=>request('entities').then(d=>{setData(d);setTab(t=>t&&d.classes.some((c:EntityClass)=>c.name===t)?t:d.classes[0]?.name||'');}).catch(e=>setError(fail(e))),[request]);
 useEffect(()=>{load();},[load]);
 const ed=useEdits(request,load);
 async function recommend(){setBusy(true);setError('');setNotice('');
  try{const r=await request('entities/recommend',{method:'POST',body:'{}'});await load();
   setNotice(r.classes||r.entities||r.same?`대상 분류 ${r.classes}개 · 새 대상 ${r.entities}개 · 같은 대상 ${r.same}개를 반영했어요.`:'새로 반영할 대상이 없어요.');}
  catch(e){setError(fail(e));}finally{setBusy(false);}}
 async function upload(){let n=0;for(const [k,v] of Object.entries(changed)){const [id,attr]=k.split('\u0000');if(await ed.post('속성 값',{entity_id:Number(id),attr,new:v.trim()===''?null:v.trim()}))n++;}
  if(n)setChanged({});}
 const C=data?.classes.find(c=>c.name===tab);
 const rows=C?.rows.filter(r=>!q||r.name.includes(q)||r.aliases.some(a=>a.includes(q)))||[];
 const links=(data?.links||[]).filter(l=>C&&(l.from===C.name||l.to===C.name));
 return <><div className="toolbar"><h1>대상</h1>{data?.can_edit&&data.has_records&&<button disabled={busy} onClick={recommend}>{busy?'AI가 기록을 보는 중이에요...':'새로 추천받기'}</button>}</div>
  <p className="muted">종이에 적힌 품목 · 설비 · 거래처 같은 대상을 AI가 알아서 등록하고, 다르게 적힌 같은 대상은 별칭으로 묶어요. 직접 고친 것은 카드로 올라가 [적용]을 눌러야 반영돼요.</p>
  {[error,ed.error].filter(Boolean).map(x=><p key={x} className="error" role="alert">{x}</p>)}{[notice,ed.notice].filter(Boolean).map(x=><p key={x} className="success" role="status">{x}</p>)}
  {!data&&!error&&<p className="muted">불러오는 중이에요...</p>}
  {data&&<EditCards cards={data.cards} busy={ed.busy} answer={ed.answer}/>}
  {data&&!data.classes.length&&<div className="empty"><h2>아직 등록된 대상이 없어요.</h2><p>품목 · 설비처럼 대상을 가리키는 칸이 든 종이를 올리면 여기에 대상 표가 생겨요.</p><button className="primary" onClick={()=>go('upload')}>올리기</button></div>}
  {!!data?.classes.length&&<>
   <div className="tabs" role="tablist">{data.classes.map(c=><button role="tab" key={c.name} aria-selected={tab===c.name} onClick={()=>{setTab(c.name);setChanged({});}}>{c.name} <span className="muted">{c.total}</span></button>)}</div>
   {C&&<section>
    <p className="muted">{[C.parent&&`상위 분류 ${C.parent}`,C.children.length&&`하위 분류 ${C.children.join(', ')}`,C.pointed_by.length&&`가리키는 칸 ${C.pointed_by.map(refText).join(', ')}`].filter(Boolean).join(' · ')}</p>
    <div className="toolbar"><input className="search" aria-label="대상 찾기" placeholder="이름이나 별칭으로 찾기" value={q} onChange={e=>setQ(e.target.value)}/>
     {data.can_edit&&!!Object.keys(changed).length&&<span className="cal-nav"><span className="muted">올리지 않은 고침 {Object.keys(changed).length}개</span><button className="primary" disabled={ed.busy} onClick={upload}>바꾼 것 올리기</button></span>}</div>
    <div className="table-wrap entity-table"><table className="plain-table"><thead><tr><th>이름</th><th>별칭</th>{C.attrs.map(a=><th key={a}>{a}</th>)}<th>기록</th></tr></thead>
     <tbody>{rows.map(r=><tr key={r.id}><td><b>{r.name}</b></td><td>{r.aliases.join(', ')||'—'}</td>
      {C.attrs.map(a=>{const k=`${r.id}\u0000${a}`;return <td key={a}>{data.can_edit?<input className="cell-input" aria-label={`${r.name} ${a}`} value={k in changed?changed[k]:(r.attrs[a]==null?'':String(r.attrs[a]))} onChange={e=>setChanged({...changed,[k]:e.target.value})}/>:show(r.attrs[a])}</td>;})}
      <td>{r.records}줄</td></tr>)}</tbody></table></div>
    {!rows.length&&<p className="muted">찾는 대상이 없어요.</p>}
    {!C.attrs.length&&<p className="muted">정보 칸이 없어요. 아래 [정보 더하기]로 단가 · 설치일 같은 정보를 더할 수 있어요.</p>}
    {data.can_edit&&<><h2>{C.name} 설정</h2><ClassTools cls={C.name} members={C.rows.map(r=>r.name)} busy={ed.busy} post={ed.post}/></>}
    {data.can_edit&&!!links.length&&<><h2>관계 정보</h2>{links.map(l=><LinkAttrs key={l.id} link={l} busy={ed.busy} post={ed.post}/>)}</>}
   </section>}</>}
  {data?.can_edit&&!!data.undoable.length&&<details className="paper-group"><summary>최근 직접 고친 것 {data.undoable.length}개</summary>
   {data.undoable.map(u=><div className="toolbar link-row" key={u.id}><span>{u.text}</span><button disabled={busy||ed.busy} onClick={async()=>{setBusy(true);setError('');setNotice('');
    try{await request(`edits/${u.id}/undo`,{method:'POST',body:'{}'});await load();setNotice('되돌렸어요.');}catch(e){setError(fail(e));}finally{setBusy(false);}}}>되돌리기</button></div>)}</details>}
  </>;
}

function NodeSettings({node,data,busy,post,edges}:{node:GraphNode,data:Graph,busy:boolean,post:Post,edges:GraphEdge[]}){
 const [unit,setUnit]=useState(''),[desc,setDesc]=useState(''),[alias,setAlias]=useState(''),[name,setName]=useState(''),[dtype,setDtype]=useState('text'),[vals,setVals]=useState<Record<string,string>>({});
 const kind=node.id[0],ref=node.id.slice(2),dot=ref.indexOf('.'),T=dot<0?ref:ref.slice(0,dot),prop=dot<0?'':ref.slice(dot+1);
 const p=kind==='P'?data.props[T]?.find(x=>x.name===prop):undefined;
 useEffect(()=>{setUnit(p?.unit||'');setDesc(p?.description||'');setAlias('');setName('');setVals({});},[node.id,p?.unit,p?.description]);
 const lab=(id:string)=>data.nodes.find(n=>n.id===id)?.label.split('\n')[0]||id;
 const out=edges.filter(e=>e.from===node.id&&(e.say||e.label)),into=edges.filter(e=>e.to===node.id&&(e.say||e.label));
 const entity=kind==='E'?node:null,eClass=entity?String(node.info.stats[0]?.[1]||''):'';
 return <section className="panel node-settings"><b>{node.info.name}</b> <small className="muted">· {node.info.kind} 설정</small>
  {(kind==='C'||kind==='E')&&<div className="rel-split"><div><small className="muted">나가는 관계</small>{out.length?out.map((e,i)=><p key={i}>{String(e.say||`${e.label} → ${lab(e.to)}`)}</p>):<p className="muted">없어요</p>}</div>
   <div><small className="muted">들어오는 관계</small>{into.length?into.map((e,i)=><p key={i}>{String(e.say||`${lab(e.from)} → ${e.label}`)}</p>):<p className="muted">없어요</p>}</div></div>}
  {kind==='P'&&p&&<><div className="pick-form"><label>단위<input value={unit} maxLength={30} onChange={e=>setUnit(e.target.value)}/></label><label>설명<input value={desc} maxLength={300} onChange={e=>setDesc(e.target.value)}/></label></div>
   <button className="primary" disabled={busy} onClick={()=>post('칸 설정',{type:T,op:'단위·설명',prop,unit,description:desc})}>단위·설명 올리기</button>
   <div className="pick-form"><label>종이에 다르게 적히는 이름<input value={alias} maxLength={200} onChange={e=>setAlias(e.target.value)} placeholder="예: 수량(개)"/></label></div>
   <button disabled={busy||!alias.trim()} onClick={async()=>{if(await post('칸 설정',{type:T,op:'다른 이름',prop,alias}))setAlias('');}}>다른 이름 더하기</button></>}
  {kind==='T'&&<><div className="pick-form"><label>새 칸 이름<input value={name} maxLength={100} onChange={e=>setName(e.target.value)}/></label>
   <label>값 종류<select value={dtype} onChange={e=>setDtype(e.target.value)}>{DTYPES.map(([k,l])=><option key={k} value={k}>{l}</option>)}</select></label>
   <label>단위<input value={unit} maxLength={30} onChange={e=>setUnit(e.target.value)}/></label></div>
   <button className="primary" disabled={busy||!name.trim()} onClick={async()=>{if(await post('칸 설정',{type:T,op:'칸 더하기',name,dtype,unit}))setName('');}}>칸 더하기</button>
   <p className="muted">칸 이름과 값의 종류는 바꾸지 않아요. 지난 기록과 지표 · 자동화가 칸 이름으로 이어져 있어요.</p></>}
  {kind==='C'&&<ClassTools cls={ref} members={data.members[ref]||[]} busy={busy} post={post}/>}
  {kind==='E'&&<>{(data.class_attrs[eClass]||[]).length?<><div className="pick-form">{data.class_attrs[eClass].map(a=><label key={a}>{a}<input value={vals[a]||''} onChange={e=>setVals({...vals,[a]:e.target.value})}/></label>)}</div>
    <button className="primary" disabled={busy||!Object.values(vals).some(v=>v.trim())} onClick={async()=>{for(const [a,v] of Object.entries(vals).filter(([,v])=>v.trim()))await post('속성 값',{entity_id:Number(ref),attr:a,new:v.trim()});setVals({});}}>바꾼 것 올리기</button></>:<p className="muted">정보 칸이 없어요. 분류 점에서 [정보 더하기]를 할 수 있어요.</p>}
   <div className="pick-form"><label>별칭<input value={alias} maxLength={200} onChange={e=>setAlias(e.target.value)}/></label></div>
   <button disabled={busy||!alias.trim()} onClick={async()=>{if(await post('같은 대상',{class:eClass,same_as:node.info.name,value:alias}))setAlias('');}}>별칭 더하기</button></>}
 </section>;
}

function GraphCanvas({nodes,edges,picked,onPick}:{nodes:GraphNode[],edges:GraphEdge[],picked:string|null,onPick:(id:string|null)=>void}){
 const ref=useRef<HTMLDivElement>(null),net=useRef<any>(null),[failed,setFailed]=useState(false);
 const pick=useRef(onPick);pick.current=onPick;
 useEffect(()=>{let alive=true;
  import('vis-network/standalone').then(({Network,DataSet})=>{if(!alive||!ref.current)return;
   const n=new Network(ref.current,{nodes:new DataSet(nodes.map(({info,...x})=>({...x,title:undefined}))) as never,edges:new DataSet(edges.map((e,i)=>({id:i,...e,font:{size:11,color:'#52525B',strokeWidth:3}}))) as never},
    {physics:{solver:'forceAtlas2Based',stabilization:{iterations:200}},interaction:{hover:true,zoomView:true,dragView:true},edges:{smooth:{enabled:true,type:'dynamic',roundness:.4},color:{color:'#A1A1AA'}},nodes:{font:{face:'Plex, sans-serif'}}});
   n.on('click',(p:{nodes:string[]})=>pick.current(p.nodes[0]||null));
   net.current=n;}).catch(()=>alive&&setFailed(true));
  return()=>{alive=false;net.current?.destroy();net.current=null;};},[nodes,edges]);
 useEffect(()=>{if(!net.current)return;if(picked)net.current.selectNodes([picked]);else net.current.unselectAll();},[picked]);
 return failed?<p className="error">그림을 그리지 못했어요.</p>:<div className="graph-wrap"><div ref={ref} className="graph" role="img" aria-label="지식그래프"/>
  <div className="zoom"><button aria-label="크게" onClick={()=>net.current?.moveTo({scale:(net.current.getScale()||1)*1.25})}>+</button><button aria-label="작게" onClick={()=>net.current?.moveTo({scale:(net.current.getScale()||1)/1.25})}>−</button></div></div>;
}

export function KnowledgeGraph({request,go}:{request:Request,go:(v:string)=>void}){
 const [withEntities,setWithEntities]=useState(false),[data,setData]=useState<Graph|null>(null),[picked,setPicked]=useState<string|null>(null);
 const [busy,setBusy]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const [a,setA]=useState(''),[b,setB]=useState(''),[kind,setKind]=useState('연결'),[name,setName]=useState('');
 const load=useCallback(()=>request(`graph?entities=${withEntities}`).then((d:Graph)=>{setData(d);setA(x=>x||d.refs[0]||'');setB(x=>x||d.refs[1]||d.refs[0]||'');}).catch(e=>setError(fail(e))),[request,withEntities]);
 useEffect(()=>{load();},[load]);
 async function act(key:string,path:string,body:object,done:string){setBusy(key);setError('');setNotice('');
  try{await request(path,{method:'POST',body:JSON.stringify(body)});await load();setNotice(done);}catch(e){setError(fail(e));}finally{setBusy('');}}
 const node=data?.nodes.find(n=>n.id===picked);
 const ed=useEdits(request,load);
 return <><div className="toolbar"><h1>지식그래프</h1>{data?.can_edit&&data.has_records&&<button disabled={!!busy} onClick={()=>act('rec','links/recommend',{},'관계 제안을 새로 올렸어요.')}>{busy==='rec'?'AI가 기록을 보는 중이에요...':'새로 추천받기'}</button>}</div>
  <p className="muted">기록 종류 · 칸 · 대상이 어떻게 이어지는지 보여 주는 그림이에요.</p>
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="success" role="status">{notice}</p>}
  {!data&&!error&&<p className="muted">불러오는 중이에요...</p>}
  {data&&!data.has_records&&<div className="empty"><h2>아직 확정한 기록이 없어요.</h2><button className="primary" onClick={()=>go('upload')}>올리기</button></div>}
  {data?.has_records&&<div className="graph-layout"><section>
    <div className="segments" aria-label="보기">{[['구조만',false],['대상까지',true]].map(([l,v])=><button key={String(l)} aria-pressed={withEntities===v} onClick={()=>{setWithEntities(v as boolean);setPicked(null);}}>{l}</button>)}</div>
    <div className="graph-box"><GraphCanvas nodes={data.nodes} edges={data.edges} picked={picked} onPick={setPicked}/>
     {node&&<aside className="node-card"><div className="toolbar"><div><b>{node.info.name}</b><small className="muted"> · {node.info.kind}</small></div><button className="text-button" aria-label="닫기" onClick={()=>setPicked(null)}>닫기</button></div>
      {node.info.desc&&<p className="muted">{node.info.desc}</p>}
      <div className="node-stats">{node.info.stats.map(([k,v])=><div key={k}><small className="muted">{k}</small><b>{v}</b></div>)}</div>
      {node.info.rels.map(r=><p key={r} className="node-rel">{r}</p>)}</aside>}</div>
    <p className="muted">청록 원 기록 종류 · 주황 상자 대상 분류 · 작은 점 칸 · 대상 정보 · 대상 · 실선 확정 · 점선 확인할 관계. 점을 누르면 그 옆에 정보와 관계가 보이고, 빈 곳을 누르면 닫혀요.</p>
    <label className="pick-node">점 고르기<select value={picked||''} onChange={e=>setPicked(e.target.value||null)}><option value="">고르세요</option>{data.nodes.map(n=><option key={n.id} value={n.id}>{n.label.replace('\n',' ')} ({n.info.kind})</option>)}</select></label>
   </section>
   <section>
    {[ed.error].filter(Boolean).map(x=><p key={x} className="error" role="alert">{x}</p>)}{[ed.notice].filter(Boolean).map(x=><p key={x} className="success" role="status">{x}</p>)}
    {node&&data.can_edit&&<NodeSettings node={node} data={data} busy={ed.busy} post={ed.post} edges={data.edges}/>}
    <EditCards cards={data.cards} busy={ed.busy} answer={ed.answer}/>
    <h2>관계 제안 {data.pending.length}개</h2>
    {!data.pending.length&&<p className="muted">확인할 관계 제안이 없어요.</p>}
    {data.pending.map(p=><article className="panel suggestion" key={p.id}><b>{p.text}</b>{p.reason&&<p>{p.reason}</p>}<p className="muted">기록으로 센 근거: {p.counted}</p>
     {data.can_edit&&<div className="card-actions"><button disabled={!!busy} onClick={()=>act(`n${p.id}`,`reviews/${p.id}`,{expected_payload:p.payload,answer:'reject'},'관계를 잇지 않았어요.')}>아니요</button>
      <button className="primary" disabled={!!busy} onClick={()=>act(`y${p.id}`,`reviews/${p.id}`,{expected_payload:p.payload,answer:'accept'},'이었어요. 그림에 실선으로 보여요.')}>맞아요</button></div>}</article>)}
    {!!data.links.length&&<><h2>확정한 관계</h2>{data.links.map(l=><div className="toolbar link-row" key={l.id}><span>{l.text}</span>{data.can_edit&&<button disabled={!!busy} onClick={()=>act(`c${l.id}`,`links/${l.id}/cut`,{},'관계를 끊었어요.')}>끊기</button>}</div>)}</>}
    {data.can_edit&&<details className="paper-group"><summary>이어져 있다고 생각하는 칸이 있나요?</summary>
     <div className="pick-form"><label>칸<select value={a} onChange={e=>setA(e.target.value)}>{data.refs.map(r=><option key={r} value={r}>{refText(r)}</option>)}</select></label>
      <label>이어질 칸<select value={b} onChange={e=>setB(e.target.value)}>{data.refs.map(r=><option key={r} value={r}>{refText(r)}</option>)}</select></label>
      <label>관계<select value={kind} onChange={e=>setKind(e.target.value)}>{data.kinds.map(k=><option key={k}>{k}</option>)}</select></label>
      <label>관계 이름(없어도 돼요)<input value={name} maxLength={100} onChange={e=>setName(e.target.value)} placeholder="예: 거래처"/></label></div>
     <button className="primary" disabled={!!busy||a===b} onClick={()=>act('link','links',{from_ref:a,to_ref:b,kind,...(name.trim()?{name:name.trim()}:{})},'관계 제안 카드로 올렸어요. [맞아요]를 눌러야 그림에 이어져요.')}>이어 보기</button></details>}
    <button onClick={()=>go('home')}>홈으로</button>
   </section></div>}</>;
}
