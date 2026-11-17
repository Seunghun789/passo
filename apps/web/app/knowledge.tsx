'use client';
import {useCallback,useEffect,useMemo,useRef,useState} from 'react';
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

// 표의 칸은 읽기로 보이고, 누르면 그 자리에서 고친다. Enter · Tab은 담고 다음 칸으로, Esc는 그대로 둔다. 고친 칸은 [바꾼 것 올리기]로 카드에 올린다.
const raw=(v:unknown)=>v==null?'':typeof v==='object'?JSON.stringify(v):String(v);
function Cell({value,changed,editing,label,onEdit,onDone}:{value:string,changed:boolean,editing:boolean,label:string,onEdit:()=>void,onDone:(v:string|null,move:number)=>void}){
 const keyed=useRef(false);useEffect(()=>{if(editing)keyed.current=false;},[editing]);  // 키로 끝냈으면 뒤따르는 blur는 넘긴다
 return <td className={changed?'changed':''}>{editing?<input autoFocus className="cell-input" aria-label={label} defaultValue={value} maxLength={1000}
  onKeyDown={e=>{if(e.key==='Escape'){e.preventDefault();keyed.current=true;onDone(null,0);}else if(e.key==='Enter'||e.key==='Tab'){e.preventDefault();keyed.current=true;onDone(e.currentTarget.value,e.shiftKey?-1:1);}}}
  onBlur={e=>{if(!keyed.current)onDone(e.currentTarget.value,0);}}/>:<button className="table-cell" aria-label={`${label} 고치기`} onClick={onEdit}>{value||<span className="muted">—</span>}</button>}</td>;
}

export function Entities({request,go}:{request:Request,go:(v:string)=>void}){
 const [data,setData]=useState<{can_edit:boolean,has_records:boolean,classes:EntityClass[],links:ClassLink[],cards:Card[],undoable:{id:number,kind:string,text:string}[]}|null>(null),[tab,setTab]=useState(''),[q,setQ]=useState('');
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[changed,setChanged]=useState<Record<string,string>>({}),[cell,setCell]=useState<string|null>(null);
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
 const pickClass=(name:string)=>{if(Object.keys(changed).length&&!window.confirm('올리지 않은 고침이 있어요. 다른 분류로 가면 사라져요.'))return;setTab(name);setChanged({});setCell(null);setQ('');};
 // 상위 분류 아래에 하위 분류를 들여 놓는다
 const order=(()=>{const cs=data?.classes||[],names=new Set(cs.map(c=>c.name)),out:{c:EntityClass,depth:number}[]=[];
  const walk=(c:EntityClass,depth:number)=>{out.push({c,depth});cs.filter(x=>x.parent===c.name).forEach(x=>walk(x,depth+1));};
  cs.filter(c=>!c.parent||!names.has(c.parent)).forEach(c=>walk(c,0));return out;})();
 const done=(r:EntityRow,a:string,v:string|null,move:number)=>{
  const k=`${r.id}\u0000${a}`,orig=raw(r.attrs[a]);
  if(v!==null)setChanged(x=>{const y={...x};if(v===orig)delete y[k];else y[k]=v;return y;});
  if(!move||!C)return setCell(null);
  const cols=C.attrs,ri=rows.findIndex(x=>x.id===r.id);let ci=cols.indexOf(a)+move,rj=ri;
  if(ci>=cols.length){ci=0;rj++;}else if(ci<0){ci=cols.length-1;rj--;}
  setCell(rows[rj]?`${rows[rj].id}\u0000${cols[ci]}`:null);};
 const pending=Object.keys(changed).length;
 return <><div className="toolbar"><h1>대상</h1>{data?.can_edit&&data.has_records&&<button disabled={busy} onClick={recommend}>{busy?'AI가 기록을 보는 중이에요...':'새로 추천받기'}</button>}</div>
  <p className="muted">종이에 적힌 품목 · 설비 · 거래처 같은 대상을 AI가 알아서 등록하고, 다르게 적힌 같은 대상은 별칭으로 묶어요.{data?.can_edit&&' 칸을 누르면 바로 고칠 수 있고, 고친 것은 카드로 올라가 [적용]을 눌러야 반영돼요.'}</p>
  {[error,ed.error].filter(Boolean).map(x=><p key={x} className="error" role="alert">{x}</p>)}{[notice,ed.notice].filter(Boolean).map(x=><p key={x} className="success" role="status">{x}</p>)}
  {!data&&!error&&<p className="muted">불러오는 중이에요...</p>}
  {data&&<EditCards cards={data.cards} busy={ed.busy} answer={ed.answer}/>}
  {data&&!data.classes.length&&<div className="empty"><h2>아직 등록된 대상이 없어요.</h2><p>품목 · 설비처럼 대상을 가리키는 칸이 든 종이를 올리면 여기에 대상 표가 생겨요.</p><button className="primary" onClick={()=>go('upload')}>올리기</button></div>}
  {!!data?.classes.length&&<div className="entity-layout">
   <nav className="class-list" role="tablist" aria-label="분류" aria-orientation="vertical"><small className="muted">분류 {data.classes.length}개</small>
    {order.map(({c,depth})=><button role="tab" key={c.name} aria-selected={tab===c.name} style={{paddingLeft:12+depth*14}} onClick={()=>pickClass(c.name)}><span>{c.name}</span><small>{c.total}</small></button>)}</nav>
   {C&&<section className="entity-main">
    <div className="toolbar"><div><h2>{C.name} <small className="muted">대상 {C.total}개</small></h2>
     {(C.parent||C.children.length>0||C.pointed_by.length>0)&&<p className="muted class-meta">{[C.parent&&`상위 분류 ${C.parent}`,C.children.length&&`하위 분류 ${C.children.join(', ')}`,C.pointed_by.length&&`가리키는 칸 ${C.pointed_by.map(refText).join(', ')}`].filter(Boolean).join(' · ')}</p>}</div>
     <input className="search" aria-label="대상 찾기" placeholder="이름이나 별칭으로 찾기" value={q} onChange={e=>setQ(e.target.value)}/></div>
    <div className="table-wrap entity-table"><table className="plain-table"><thead><tr><th>이름</th><th>별칭</th>{C.attrs.map(a=><th key={a}>{a}</th>)}<th>기록</th></tr></thead>
     <tbody>{rows.map(r=><tr key={r.id}><th scope="row">{r.name}</th><td>{r.aliases.join(', ')||<span className="muted">—</span>}</td>
      {C.attrs.map(a=>{const k=`${r.id}\u0000${a}`,v=k in changed?changed[k]:raw(r.attrs[a]);
       return data.can_edit?<Cell key={a} value={v} changed={k in changed} editing={cell===k} label={`${r.name} ${a}`} onEdit={()=>setCell(k)} onDone={(x,m)=>done(r,a,x,m)}/>:<td key={a}>{v||'—'}</td>;})}
      <td>{r.records}줄</td></tr>)}</tbody></table>
     {!rows.length&&<p className="muted table-note">찾는 대상이 없어요.</p>}</div>
    {data.can_edit&&pending>0&&<div className="save-bar" role="status"><span>고친 칸 {pending}개 · 올리면 카드로 보여요</span><button className="primary" disabled={ed.busy} onClick={upload}>바꾼 것 올리기</button></div>}
    {!C.attrs.length&&<p className="muted">정보 칸이 없어요. 아래에서 [정보 더하기]로 단가 · 설치일 같은 정보를 더할 수 있어요.</p>}
    {data.can_edit&&<details className="paper-group"><summary>정보 더하기 · 별칭 · 묶기</summary><ClassTools cls={C.name} members={C.rows.map(r=>r.name)} busy={ed.busy} post={ed.post}/></details>}
    {data.can_edit&&!!links.length&&<details className="paper-group"><summary>관계 정보 <span>{links.length}개</span></summary>{links.map(l=><LinkAttrs key={l.id} link={l} busy={ed.busy} post={ed.post}/>)}</details>}
   </section>}</div>}
  {data?.can_edit&&!!data.undoable.length&&<details className="paper-group"><summary>최근 직접 고친 것 <span>{data.undoable.length}개</span></summary>
   {data.undoable.map(u=><div className="toolbar link-row" key={u.id}><span>{u.text}</span><button disabled={busy||ed.busy} onClick={async()=>{setBusy(true);setError('');setNotice('');
    try{await request(`edits/${u.id}/undo`,{method:'POST',body:'{}'});await load();setNotice('되돌렸어요.');}catch(e){setError(fail(e));}finally{setBusy(false);}}}>되돌리기</button></div>)}</details>}
  </>;
}

function NodeSettings({node,data,busy,post}:{node:GraphNode,data:Graph,busy:boolean,post:Post}){
 const [unit,setUnit]=useState(''),[desc,setDesc]=useState(''),[alias,setAlias]=useState(''),[name,setName]=useState(''),[dtype,setDtype]=useState('text'),[vals,setVals]=useState<Record<string,string>>({});
 const kind=node.id[0],ref=node.id.slice(2),dot=ref.indexOf('.'),T=dot<0?ref:ref.slice(0,dot),prop=dot<0?'':ref.slice(dot+1);
 const p=kind==='P'?data.props[T]?.find(x=>x.name===prop):undefined;
 useEffect(()=>{setUnit(p?.unit||'');setDesc(p?.description||'');setAlias('');setName('');setVals({});},[node.id,p?.unit,p?.description]);
 const entity=kind==='E'?node:null,eClass=entity?String(node.info.stats[0]?.[1]||''):'';
 if(kind==='A')return null;
 return <details className="paper-group node-settings" key={node.id}><summary>{node.info.name} 설정 <span>{node.info.kind}</span></summary>
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
 </details>;
}

// 점 모양: 기록 종류 · 대상 분류는 이름을 점 아래에 크게 써서, 멀리서 봐도 이름이 읽힌다. 칸 · 정보 · 대상의 이름은 가까이 볼 때만.
const MAIN:Record<string,object>={T:{shape:'dot',size:18},C:{shape:'square',size:13}};
const INK='#18181B',FADE=0.12;
const mainFont=(scale:number)=>({size:Math.min(110,Math.max(15,14/scale)),color:INK,face:'Plex, sans-serif',strokeWidth:5,strokeColor:'#ffffff',bold:{color:INK}});
// 다른 점과 관계가 없는 칸 · 정보(제 기록 종류 · 분류에만 붙은 점)는 접어 두고, 그 기록 종류 · 분류를 누르면 펼친다
function leaves(nodes:GraphNode[],edges:GraphEdge[]){
 const deg:Record<string,number>={};edges.forEach(e=>{deg[e.from]=(deg[e.from]||0)+1;deg[e.to]=(deg[e.to]||0)+1;});
 const owner:Record<string,string>={};
 nodes.forEach(n=>{if((n.id[0]==='P'||n.id[0]==='A')&&deg[n.id]===1){const e=edges.find(x=>x.to===n.id&&x.from[0]===(n.id[0]==='P'?'T':'C'));if(e)owner[n.id]=e.from;}});
 return owner;
}
function GraphCanvas({nodes,edges,picked,onPick}:{nodes:GraphNode[],edges:GraphEdge[],picked:string|null,onPick:(id:string|null)=>void}){
 const ref=useRef<HTMLDivElement>(null),net=useRef<any>(null),sets=useRef<{n:any,e:any}|null>(null),[failed,setFailed]=useState(false),[ready,setReady]=useState(false);
 const pick=useRef(onPick);pick.current=onPick;const was=useRef<string|null>(null);
 const folded=useMemo(()=>leaves(nodes,edges),[nodes,edges]);
 useEffect(()=>{let alive=true;setReady(false);
  import('vis-network/standalone').then(({Network,DataSet})=>{if(!alive||!ref.current)return;
   const n=new DataSet(nodes.map(({info,...x})=>({...x,title:undefined,...(MAIN[x.id[0]]?{...MAIN[x.id[0]],font:mainFont(1)}:{}),hidden:x.id in folded})) as never);
   const e=new DataSet(edges.map((x,i)=>({id:i,...x,font:{size:11,color:'#52525B',strokeWidth:3}})) as never);
   const w=new Network(ref.current,{nodes:n,edges:e} as never,
    {physics:{solver:'forceAtlas2Based',forceAtlas2Based:{gravitationalConstant:-160,centralGravity:.006,springLength:150,avoidOverlap:.8},stabilization:{iterations:300,fit:true}},
     interaction:{hover:true,zoomView:true,dragView:true,tooltipDelay:200},edges:{smooth:{enabled:true,type:'continuous',roundness:.3},color:{color:'#A1A1AA'}},
     nodes:{font:{face:'Plex, sans-serif',size:12},scaling:{label:{drawThreshold:7}}}});
   const grow=(scale:number)=>(n as any).update((n as any).getIds().filter((id:string)=>MAIN[id[0]]).map((id:string)=>({id,font:mainFont(scale)})));
   let last=0;w.on('afterDrawing',()=>{const k=w.getScale();if(Math.abs(k-last)/k>.08){last=k;grow(k);}});  // 손으로 · 버튼으로 · 움직임으로 바뀐 배율 모두
   w.once('stabilizationIterationsDone',()=>{w.setOptions({physics:{enabled:false}});w.fit({animation:false});alive&&setReady(true);});
   w.on('click',(p:{nodes:string[]})=>pick.current(p.nodes[0]||null));
   net.current=w;sets.current={n,e};}).catch(()=>alive&&setFailed(true));
  return()=>{alive=false;net.current?.destroy();net.current=null;sets.current=null;};},[nodes,edges,folded]);
 useEffect(()=>{const w=net.current,S=sets.current;if(!w||!S)return;  // 누른 점과 바로 이어진 점만 또렷하게, 나머지는 흐리게
  const near=new Set<string>(picked?[picked]:[]);
  if(picked)edges.forEach(e=>{if(e.from===picked)near.add(e.to);if(e.to===picked)near.add(e.from);});
  S.n.update(nodes.map(x=>({id:x.id,hidden:x.id in folded&&!(picked&&(folded[x.id]===picked||near.has(x.id))),opacity:!picked||near.has(x.id)?1:FADE})));
  S.e.update(edges.map((x,i)=>{const on=!picked||x.from===picked||x.to===picked;return {id:i,color:{color:String((x as any).color||'#A1A1AA'),opacity:on?1:FADE},font:{size:11,color:on?'#52525B':'#52525B00',strokeWidth:on?3:0}};}));
  if(picked){w.selectNodes([picked]);w.fit({nodes:[...near],maxZoomLevel:1.1,animation:{duration:450,easingFunction:'easeInOutQuad'}});}
  else{w.unselectAll();if(was.current)w.fit({animation:{duration:400,easingFunction:'easeInOutQuad'}});}was.current=picked;},[picked,nodes,edges,folded,ready]);
 const zoom=(k:number)=>net.current?.moveTo({scale:(net.current.getScale()||1)*k,animation:{duration:200}});
 return failed?<p className="error">그림을 그리지 못했어요.</p>:<div className="graph-wrap"><div ref={ref} className="graph" role="img" aria-label="지식그래프"/>
  {!ready&&<p className="graph-loading muted">점을 놓는 중이에요...</p>}
  <div className="zoom"><button aria-label="크게" onClick={()=>zoom(1.25)}>+</button><button aria-label="작게" onClick={()=>zoom(1/1.25)}>−</button></div></div>;
}

// 누른 점의 카드: 숫자 세 개, 짜임(칸 · 정보 칸 · 가리키는 칸)은 한 줄씩, 관계는 "→ 이어진 점 · 관계 이름" 짧은 줄로. 관계는 5개까지 보이고 나머지는 접는다
function NodeCard({node,data,onPick}:{node:GraphNode,data:Graph,onPick:(id:string|null)=>void}){
 const lab=(id:string)=>data.nodes.find(n=>n.id===id)?.label.split('\n')[0]||id;
 const mine=data.edges.filter(e=>e.from===node.id||e.to===node.id);
 const groups:Record<string,string[]>={};
 mine.forEach(e=>{const r=e.rel as string[]|undefined;if(!r)return;const out=e.from===node.id;(groups[r[out?0:1]]??=[]).push(lab(out?e.to:e.from));});
 const rels=mine.filter(e=>!e.rel&&(e.label||e.say)).map(e=>{const out=e.from===node.id;return {out,id:out?e.to:e.from,name:String(e.label||'').replace(/\?$/,'').replace(/ \(.*\)$/,''),wait:!!e.dashes};})
  .sort((x,y)=>Number(x.wait)-Number(y.wait));
 const row=(r:typeof rels[number],i:number)=><button key={i} className="rel-row" onClick={()=>onPick(r.id)} title={`${lab(r.id)} 점으로 가기`}>
  <span className="muted">{r.out?'→':'←'}</span><b>{lab(r.id)}</b>{r.name&&r.name!==lab(r.id)&&<small className="muted">{r.name}</small>}{r.wait&&<span className="tag gap">확인할 관계</span>}</button>;
 return <aside className="node-card"><div className="toolbar"><div><b>{node.info.name}</b><small className="muted"> · {node.info.kind}</small></div><button className="text-button" onClick={()=>onPick(null)}>닫기</button></div>
  {node.info.desc&&<p className="muted node-desc" title={node.info.desc}>{node.info.desc}</p>}
  <div className="node-stats">{node.info.stats.map(([k,v])=><div key={k}><small className="muted">{k}</small><b>{v}</b></div>)}</div>
  {Object.entries(groups).map(([k,v])=><p key={k} className="node-group" title={[...new Set(v)].join(', ')}><small className="muted">{k} {v.length}</small>{[...new Set(v)].join(', ')}</p>)}
  {!!rels.length&&<div className="rel-rows"><small className="muted">관계 {rels.length}개</small>{rels.slice(0,5).map(row)}
   {rels.length>5&&<details><summary className="muted">나머지 {rels.length-5}개</summary>{rels.slice(5).map((r,i)=>row(r,i+5))}</details>}</div>}
 </aside>;
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
     {node&&<NodeCard key={node.id} node={node} data={data} onPick={setPicked}/>}</div>
    <ul className="legend" aria-label="그림 읽는 법"><li><i className="dot t"/>기록 종류</li><li><i className="dot c"/>대상 분류</li><li><i className="dot p"/>칸</li><li><i className="dot a"/>대상 정보</li>{withEntities&&<li><i className="dot e"/>대상</li>}<li><i className="ln"/>확정</li><li><i className="ln dash"/>확인할 관계</li></ul>
    <p className="muted">점을 누르면 바로 이어진 점만 또렷해지고, 접혀 있던 칸이 펼쳐져요. 빈 곳을 누르면 처음으로 돌아가요.</p>
    <label className="pick-node">점 고르기<select value={picked||''} onChange={e=>setPicked(e.target.value||null)}><option value="">고르세요</option>{data.nodes.map(n=><option key={n.id} value={n.id}>{n.label.replace('\n',' ')} ({n.info.kind})</option>)}</select></label>
   </section>
   <section>
    {[ed.error].filter(Boolean).map(x=><p key={x} className="error" role="alert">{x}</p>)}{[ed.notice].filter(Boolean).map(x=><p key={x} className="success" role="status">{x}</p>)}
    {node&&data.can_edit&&<NodeSettings node={node} data={data} busy={ed.busy} post={ed.post}/>}
    <EditCards cards={data.cards} busy={ed.busy} answer={ed.answer}/>
    <h2>관계 제안 {data.pending.length}개</h2>
    {!data.pending.length&&<p className="muted">확인할 관계 제안이 없어요.</p>}
    {data.pending.map(p=><article className="panel suggestion" key={p.id}><b>{p.text}</b>{p.reason&&<p>{p.reason}</p>}<p className="muted">기록으로 센 근거: {p.counted}</p>
     {data.can_edit&&<div className="card-actions"><button disabled={!!busy} onClick={()=>act(`n${p.id}`,`reviews/${p.id}`,{expected_payload:p.payload,answer:'reject'},'관계를 잇지 않았어요.')}>아니요</button>
      <button className="primary" disabled={!!busy} onClick={()=>act(`y${p.id}`,`reviews/${p.id}`,{expected_payload:p.payload,answer:'accept'},'이었어요. 그림에 실선으로 보여요.')}>맞아요</button></div>}</article>)}
    {!!data.links.length&&<details className="paper-group"><summary>확정한 관계 <span>{data.links.length}개</span></summary>{data.links.map(l=><div className="toolbar link-row" key={l.id}><span>{l.text}</span>{data.can_edit&&<button disabled={!!busy} onClick={()=>act(`c${l.id}`,`links/${l.id}/cut`,{},'관계를 끊었어요.')}>끊기</button>}</div>)}</details>}
    {data.can_edit&&<details className="paper-group"><summary>이어져 있다고 생각하는 칸이 있나요?</summary>
     <div className="pick-form"><label>칸<select value={a} onChange={e=>setA(e.target.value)}>{data.refs.map(r=><option key={r} value={r}>{refText(r)}</option>)}</select></label>
      <label>이어질 칸<select value={b} onChange={e=>setB(e.target.value)}>{data.refs.map(r=><option key={r} value={r}>{refText(r)}</option>)}</select></label>
      <label>관계<select value={kind} onChange={e=>setKind(e.target.value)}>{data.kinds.map(k=><option key={k}>{k}</option>)}</select></label>
      <label>관계 이름(없어도 돼요)<input value={name} maxLength={100} onChange={e=>setName(e.target.value)} placeholder="예: 거래처"/></label></div>
     <button className="primary" disabled={!!busy||a===b} onClick={()=>act('link','links',{from_ref:a,to_ref:b,kind,...(name.trim()?{name:name.trim()}:{})},'관계 제안 카드로 올렸어요. [맞아요]를 눌러야 그림에 이어져요.')}>이어 보기</button></details>}
    <button onClick={()=>go('home')}>홈으로</button>
   </section></div>}</>;
}
