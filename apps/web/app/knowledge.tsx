'use client';
import {useCallback,useEffect,useRef,useState} from 'react';
type Request=(path:string,init?:RequestInit)=>Promise<any>;
type EntityRow={id:number,name:string,aliases:string[],attrs:Record<string,unknown>,records:number};
type EntityClass={name:string,parent:string|null,attrs:string[],total:number,rows:EntityRow[],children:string[],pointed_by:string[]};
type Info={name:string,kind:string,desc:string,stats:[string,string][],rels:string[],count:number};
type GraphNode={id:string,label:string,info:Info,[k:string]:unknown};
type GraphEdge={from:string,to:string,[k:string]:unknown};
type Pending={id:number,payload:Record<string,unknown>,text:string,reason?:string,counted?:string};
type Graph={can_edit:boolean,has_records:boolean,nodes:GraphNode[],edges:GraphEdge[],links:{id:number,text:string}[],pending:Pending[],refs:string[],kinds:string[]};
const show=(v:unknown)=>v===null||v===undefined||v===''?'—':typeof v==='object'?JSON.stringify(v):String(v);
const fail=(e:unknown)=>{const m=(e as Error).message;return m==='요청을 처리하지 못했어요. 다시 시도해 주세요.'?'잠시 뒤 다시 눌러 주세요.':m;};
const refText=(r:string)=>{const i=r.indexOf('.');return i<0?r:`${r.slice(i+1)}(${r.slice(0,i)})`;};

export function Entities({request,go}:{request:Request,go:(v:string)=>void}){
 const [data,setData]=useState<{can_edit:boolean,has_records:boolean,classes:EntityClass[]}|null>(null),[tab,setTab]=useState(''),[q,setQ]=useState('');
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const load=useCallback(()=>request('entities').then(d=>{setData(d);setTab(t=>t&&d.classes.some((c:EntityClass)=>c.name===t)?t:d.classes[0]?.name||'');}).catch(e=>setError(fail(e))),[request]);
 useEffect(()=>{load();},[load]);
 async function recommend(){setBusy(true);setError('');setNotice('');
  try{const r=await request('entities/recommend',{method:'POST',body:'{}'});await load();
   setNotice(r.classes||r.entities||r.same?`대상 분류 ${r.classes}개 · 새 대상 ${r.entities}개 · 같은 대상 ${r.same}개를 반영했어요.`:'새로 반영할 대상이 없어요.');}
  catch(e){setError(fail(e));}finally{setBusy(false);}}
 const C=data?.classes.find(c=>c.name===tab);
 const rows=C?.rows.filter(r=>!q||r.name.includes(q)||r.aliases.some(a=>a.includes(q)))||[];
 return <><div className="toolbar"><h1>대상</h1>{data?.can_edit&&data.has_records&&<button disabled={busy} onClick={recommend}>{busy?'AI가 기록을 보는 중이에요...':'새로 추천받기'}</button>}</div>
  <p className="muted">종이에 적힌 품목 · 설비 · 거래처 같은 대상을 AI가 알아서 등록하고, 다르게 적힌 같은 대상은 별칭으로 묶어요.</p>
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="success" role="status">{notice}</p>}
  {!data&&!error&&<p className="muted">불러오는 중이에요...</p>}
  {data&&!data.classes.length&&<div className="empty"><h2>아직 등록된 대상이 없어요.</h2><p>품목 · 설비처럼 대상을 가리키는 칸이 든 종이를 올리면 여기에 대상 표가 생겨요.</p><button className="primary" onClick={()=>go('upload')}>올리기</button></div>}
  {!!data?.classes.length&&<>
   <div className="tabs" role="tablist">{data.classes.map(c=><button role="tab" key={c.name} aria-selected={tab===c.name} onClick={()=>setTab(c.name)}>{c.name} <span className="muted">{c.total}</span></button>)}</div>
   {C&&<section>
    <p className="muted">{[C.parent&&`상위 분류 ${C.parent}`,C.children.length&&`하위 분류 ${C.children.join(', ')}`,C.pointed_by.length&&`가리키는 칸 ${C.pointed_by.map(refText).join(', ')}`].filter(Boolean).join(' · ')}</p>
    <input className="search" aria-label="대상 찾기" placeholder="이름이나 별칭으로 찾기" value={q} onChange={e=>setQ(e.target.value)}/>
    <div className="table-wrap entity-table"><table className="plain-table"><thead><tr><th>이름</th><th>별칭</th>{C.attrs.map(a=><th key={a}>{a}</th>)}<th>기록</th></tr></thead>
     <tbody>{rows.map(r=><tr key={r.id}><td><b>{r.name}</b></td><td>{r.aliases.join(', ')||'—'}</td>{C.attrs.map(a=><td key={a}>{show(r.attrs[a])}</td>)}<td>{r.records}줄</td></tr>)}</tbody></table></div>
    {!rows.length&&<p className="muted">찾는 대상이 없어요.</p>}
   </section>}</>}</>;
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
