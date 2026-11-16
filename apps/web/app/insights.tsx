'use client';
import {Fragment,useCallback,useEffect,useState} from 'react';
type Request=(path:string,init?:RequestInit)=>Promise<any>;
type Table={columns:string[],rows:{id:number,source_id?:number|null,values:Record<string,unknown>}[],total:number};
type Alert={id:number,title:string,type:string,rule:string,chip:string,kind:string,count:number,until:string,headline?:string|null,targets?:{name:string,why:string}[],follow?:{name:string,why:string}[],evidence?:Table};
type Suggestion={title:string,type:string,rule:string,reason?:string,count:number,backtest:number,chip:string,schedule?:{text:string,hit:number,of:number}|null,evidence:Table};
type Glance={title:string,value:string,previous:string,previous_label:string,evidence:number};
type HomeData={enabled:number,alerts:Alert[],more:{title:string,count:number}[],quiet:string[],glance:Glance[]};
type Series={lines:string[],points:Record<string,unknown>[]};
type Widget={id?:number,title:string,kind:'number'|'trend',value?:string,previous?:string,previous_label?:string,until:string,reason?:string,series?:Series,evidence:Table};
const PERIODS=['오늘','이번 주','이번 달','올해'];
const COLORS=['#4F46E5','#D97706','#DB2777','#65A30D','#1F1F1F','#A1A1AA'];
const show=(v:unknown)=>v===null||v===undefined||v===''?'—':typeof v==='object'?JSON.stringify(v):String(v);
const fail=(e:unknown)=>{const m=(e as Error).message;return m==='요청을 처리하지 못했어요. 다시 시도해 주세요.'?'잠시 뒤 다시 눌러 주세요.':m;};

export function Evidence({table,tid,label}:{table:Table,tid:number,label?:string}){
 const [open,setOpen]=useState<number|null>(null);
 if(!table.total)return null;
 return <details className="proof"><summary>{label||`근거 기록 ${table.total}줄`}</summary>
  <div className="table-wrap"><table className="plain-table"><thead><tr>{table.columns.map(c=><th key={c}>{c}</th>)}</tr></thead>
  <tbody>{table.rows.map(r=><Fragment key={r.id}><tr className={r.source_id?'clickable':''} onClick={()=>r.source_id&&setOpen(open===r.id?null:r.id)}>{table.columns.map(c=><td key={c}>{show(r.values[c])}</td>)}</tr>
   {open===r.id&&r.source_id&&<tr><td colSpan={table.columns.length}><img className="evidence-photo" src={`/api/workspaces/${tid}/business/sources/${r.source_id}/original?page=1`} alt="원본 사진"/></td></tr>}</Fragment>)}</tbody></table></div>
  {table.total>table.rows.length&&<p className="muted">앞의 {table.rows.length}줄만 보여요.</p>}</details>;
}

function Line({series,title}:{series:Series,title:string}){
 const W=560,H=180,P=28,pts=series.points;
 const vals=pts.flatMap(p=>series.lines.map(l=>p[l])).filter((v):v is number=>typeof v==='number');
 if(pts.length<1||!vals.length)return <p className="muted">이 기간에는 그릴 값이 없어요.</p>;
 const min=Math.min(...vals),max=Math.max(...vals),lo=min===max?min-1:min,hi=min===max?max+1:max,span=hi-lo;
 const x=(i:number)=>P+(pts.length<2?(W-2*P)/2:i*(W-2*P)/(pts.length-1)),y=(v:number)=>H-P-(v-lo)*(H-2*P)/span;
 return <figure className="line-chart"><svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title} 추이`}>
  <line x1={P} x2={W-P} y1={H-P} y2={H-P} className="axis"/>
  <text x={4} y={y(max)+4} className="tick">{max.toLocaleString()}</text>{min!==max&&<text x={4} y={y(min)+4} className="tick">{min.toLocaleString()}</text>}
  {series.lines.map((l,k)=>{const d=pts.map((p,i)=>typeof p[l]==='number'?`${x(i)},${y(p[l] as number)}`:null).filter(Boolean);
   return <g key={l}><polyline fill="none" stroke={COLORS[k%COLORS.length]} strokeWidth={2} points={d.join(' ')}/>{d.map((c,i)=>{const [cx,cy]=(c as string).split(',');return <circle key={i} cx={cx} cy={cy} r={2.5} fill={COLORS[k%COLORS.length]}/>;})}</g>;})}
  <text x={P} y={H-8} className="tick">{String(pts[0].date).slice(5)}</text><text x={W-P} y={H-8} textAnchor="end" className="tick">{String(pts[pts.length-1].date).slice(5)}</text>
 </svg>{series.lines.length>1&&<figcaption>{series.lines.map((l,k)=><span key={l}><i style={{background:COLORS[k%COLORS.length]}}/>{l}</span>)}</figcaption>}</figure>;
}

export function Periods({period,set}:{period:string,set:(p:string)=>void}){
 return <div className="segments" aria-label="보는 기간">{PERIODS.map(p=><button aria-pressed={period===p} key={p} onClick={()=>set(p)}>{p}</button>)}</div>;
}

export function HomeAlerts({request,tid,period,go,onCount,feed}:{request:Request,tid:number,period:string,go:(v:string)=>void,onCount:(n:number)=>void,feed:React.ReactNode}){
 const [data,setData]=useState<HomeData|null>(null),[error,setError]=useState('');
 useEffect(()=>{let alive=true;request(`home?period=${encodeURIComponent(period)}`).then((d:HomeData)=>{if(alive){setData(d);onCount(d.alerts.length+d.more.length);}}).catch(e=>alive&&setError(fail(e)));return()=>{alive=false;};},[request,period,onCount]);
 if(error)return <p className="error" role="alert">{error}</p>;
 if(!data)return <p className="muted">켜 둔 자동화를 세는 중이에요...</p>;
 return <>{data.alerts.map(a=><AlertCard key={a.id} a={a} tid={tid} go={go}/>)}
  {!data.enabled&&<p className="muted">자동화에서 업무를 켜 두면 걸린 대상이 여기에 알아서 보여요.</p>}
  {!!data.enabled&&!data.alerts.length&&<p className="muted">켜 둔 자동화 {data.enabled}개 · 오늘은 걸린 것이 없어요.</p>}
  {(!!data.more.length||!!data.quiet.length)&&<details className="more-alerts"><summary>{[data.more.length?`더 걸린 자동화 ${data.more.length}개`:'',data.quiet.length?`걸린 것이 없는 자동화 ${data.quiet.length}개`:''].filter(Boolean).join(' · ')}</summary>
   {data.more.map(m=><p key={m.title} className="muted">{m.title}: {m.count}건</p>)}{data.quiet.map(q=><p key={q} className="muted">{q}: 걸린 것 없음</p>)}</details>}
  <div className="home-columns">{feed}<GlanceRow items={data.glance} period={period}/></div></>;
}

function GlanceRow({items,period}:{items:Glance[],period:string}){
 return <section className="glance">{!items.length?null:<><b>{period} 한눈에</b><div className="metrics">{items.map(g=><div className="panel metric" key={g.title}><span>{g.title}</span><strong>{g.value}</strong><small>{g.previous_label} {g.previous} · 근거 {g.evidence}줄</small></div>)}</div><p className="muted">숫자는 모두 기록에서 셌어요.</p></>}</section>;
}

function AlertCard({a,tid,go}:{a:Alert,tid:number,go:(v:string)=>void}){
 return <article className={`panel alert ${a.kind}`}><div className="alert-head"><span className={`tag ${a.kind}`}>{a.chip}</span><span>켜 둔 자동화 &apos;{a.title}&apos; · {a.count}건</span></div>
  {a.headline&&<h3>{a.headline}</h3>}
  {a.targets?.map(t=><div className="target" key={t.name+t.why}><b>{t.name}</b><p>왜: {t.why}</p>{!!a.follow?.length&&<p>안 보면: {a.follow.map(f=>`${f.name} (${f.why})`).join(', ')}</p>}</div>)}
  {a.count>(a.targets?.length||0)&&<p className="muted">그 밖에 {a.count-(a.targets?.length||0)}건은 근거에서 봐요.</p>}
  <div className="alert-foot"><small>근거 {a.count}줄 · {a.until}</small>{(a.kind==='gap'||a.kind==='due')&&<button className="primary" onClick={()=>go('upload')}>사진 올리기</button>}<button onClick={()=>go('ask')}>묻기로 가기</button></div>
  {a.evidence&&<Evidence table={a.evidence} tid={tid}/>}</article>;
}

export function WeekSummary({request,tid}:{request:Request,tid:number}){
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[data,setData]=useState<{lines:{text:string,evidence:Table}[],facts:{name:string,now:string,before:string,diff:string,evidence:number}[]}|null>(null);
 async function make(){setBusy(true);setError('');try{setData(await request('week-summary',{method:'POST',body:'{}'}));}catch(e){setError(fail(e));}finally{setBusy(false);}}
 return <><button className="weekly-button" disabled={busy} onClick={make}>{busy?'이번 주 기록을 세는 중이에요...':'이번 주 요약 만들기'}</button>
  {error&&<p className="error" role="alert">{error}</p>}
  {data&&<section className="panel week"><small className="muted">이번 주 요약: 오늘까지 7일과 그 전 7일</small>{data.lines.map((l,i)=><div key={i}><p>{l.text}</p><Evidence table={l.evidence} tid={tid}/></div>)}
   <details className="proof"><summary>센 숫자</summary><div className="table-wrap"><table className="plain-table"><thead><tr><th>이름</th><th>이번 주</th><th>지난주</th><th>차이</th><th>근거</th></tr></thead><tbody>{data.facts.map(f=><tr key={f.name}><td>{f.name}</td><td>{f.now}</td><td>{f.before}</td><td>{f.diff}</td><td>{f.evidence}줄</td></tr>)}</tbody></table></div></details></section>}</>;
}

function useLoad<T>(request:Request,path:string){
 const [data,setData]=useState<T|null>(null),[error,setError]=useState('');
 const load=useCallback(()=>request(path).then((d:T)=>{setData(d);setError('');}).catch(e=>setError(fail(e))),[request,path]);
 useEffect(()=>{load();},[load]);
 return {data,error,setError,load};
}

export function Automation({request,tid,go}:{request:Request,tid:number,go:(v:string)=>void}){
 const {data,error,setError,load}=useLoad<{can_edit:boolean,has_records:boolean,enabled:Alert[],off:{id:number,title:string}[],suggestions:Suggestion[]}>(request,'automations');
 const [busy,setBusy]=useState(''),[notice,setNotice]=useState('');
 async function act(key:string,path:string,body:object,done:string){setBusy(key);setNotice('');try{await request(path,{method:'POST',body:JSON.stringify(body)});await load();setNotice(done);}catch(e){setError(fail(e));}finally{setBusy('');}}
 return <><h1>자동화</h1><p className="muted">켜 둔 자동화는 홈의 &apos;오늘 먼저 볼 것&apos;에 보여요.</p>
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="success" role="status">{notice}</p>}
  {!data&&!error&&<p className="muted">불러오는 중이에요...</p>}
  {data&&!data.has_records&&<div className="empty"><h2>아직 확정한 기록이 없어요.</h2><button className="primary" onClick={()=>go('upload')}>올리기</button></div>}
  {data?.has_records&&<>
   {!!data.suggestions.length&&<><h2>반복 업무 제안</h2>{data.suggestions.map(s=><article className="panel suggestion" key={s.title}>
    <div className="alert-head"><span className="tag">{s.chip}</span><b>{s.title}</b></div><p className="muted">{s.rule}</p>{s.reason&&<p>{s.reason}</p>}
    {s.schedule&&<p className="muted">최근 {s.schedule.of}번 중 {s.schedule.hit}번이 {s.schedule.text}</p>}
    <p>지금 걸린 것 {s.count}건 · 지난 30일이었다면 {s.backtest}번 걸렸어요 (근거 {s.backtest}줄)</p>
    <Evidence table={s.evidence} tid={tid} label={`지금 걸린 기록 ${s.evidence.total}줄`}/>
    {data.can_edit&&<div className="card-actions"><button className="primary" disabled={!!busy} onClick={()=>act(s.title,'automations',{title:s.title},'켰어요. 홈에도 보여요.')}>켜기</button></div>}
    <small className="muted">알림을 보내거나 기록을 바꾸지는 않아요.</small></article>)}</>}
   <h2>켜 둔 자동화</h2>{data.enabled.map(a=><article className="panel" key={a.id}><div className="toolbar"><div><b>{a.title}</b>, 지금 {a.count}건<p className="muted">{a.rule}</p></div>
    {data.can_edit&&<button disabled={!!busy} onClick={()=>act(`off${a.id}`,`automations/${a.id}`,{status:'꺼짐'},'껐어요. 홈에서 빠져요.')}>끄기</button>}</div>
    {a.evidence&&<Evidence table={a.evidence} tid={tid} label={`걸린 기록 ${a.count}줄`}/>}</article>)}
   {!data.enabled.length&&<p className="muted">켜 둔 자동화가 없어요.</p>}
   {!!data.off.length&&<details className="paper-group"><summary>꺼 둔 자동화 {data.off.length}개</summary>{data.off.map(a=><div className="toolbar" key={a.id}><span>{a.title}</span>{data.can_edit&&<button disabled={!!busy} onClick={()=>act(`on${a.id}`,`automations/${a.id}`,{status:'켜짐'},'다시 켰어요. 홈에 보여요.')}>다시 켜기</button>}</div>)}</details>}
   {!data.suggestions.length&&!data.enabled.length&&<p className="muted">관계를 확정하거나 기록이 쌓이면 반복 업무 제안이 올라와요.</p>}
  </>}</>;
}

function WidgetCard({w,tid,action}:{w:Widget,tid:number,action?:React.ReactNode}){
 return <article className="panel widget"><div className="toolbar"><b>{w.title}</b>{action}</div>
  {w.kind==='number'?<><strong className="big-number">{w.value}</strong><small className="muted">{w.previous_label} {w.previous} · {w.until}</small></>:<>{w.series&&<Line series={w.series} title={w.title}/>}<small className="muted">{w.until}</small></>}
  {w.reason&&<p className="muted">{w.reason}</p>}
  <Evidence table={w.evidence} tid={tid}/></article>;
}

export function Dashboard({request,tid,go}:{request:Request,tid:number,go:(v:string)=>void}){
 const [period,setPeriod]=useState('이번 주');
 const {data,error,setError,load}=useLoad<{can_edit:boolean,has_records:boolean,auto:Widget[],widgets:Widget[],down:{id:number,title:string}[],suggestions:Widget[]}>(request,`dashboard?period=${encodeURIComponent(period)}`);
 const [busy,setBusy]=useState(''),[notice,setNotice]=useState('');
 async function act(key:string,path:string,body:object,done:string){setBusy(key);setNotice('');try{await request(path,{method:'POST',body:JSON.stringify(body)});await load();setNotice(done);}catch(e){setError(fail(e));}finally{setBusy('');}}
 return <><h1>대시보드</h1><p className="muted">확정한 기록으로 저절로 그려요. 숫자는 모두 기록에서 셌어요.</p>
  <Periods period={period} set={setPeriod}/>
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="success" role="status">{notice}</p>}
  {!data&&!error&&<p className="muted">불러오는 중이에요...</p>}
  {data&&!data.has_records&&<div className="empty"><h2>아직 확정한 기록이 없어요.</h2><button className="primary" onClick={()=>go('upload')}>올리기</button></div>}
  {data?.has_records&&<>
   {!!data.suggestions.length&&<><h2>추천 지표</h2><div className="widget-grid">{data.suggestions.map(w=><WidgetCard key={w.title} w={w} tid={tid} action={data.can_edit&&<button className="primary" disabled={!!busy} onClick={()=>act(w.title,'widgets',{title:w.title},'올렸어요.')}>올리기</button>}/>)}</div></>}
   <h2>올린 지표</h2>{data.widgets.length?<div className="widget-grid">{data.widgets.map(w=><WidgetCard key={w.id} w={w} tid={tid} action={data.can_edit&&<button disabled={!!busy} onClick={()=>act(`d${w.id}`,`widgets/${w.id}`,{status:'내림'},'내렸어요.')}>내리기</button>}/>)}</div>:<p className="muted">올린 지표가 없어요.</p>}
   {!!data.down.length&&<details className="paper-group"><summary>내린 지표 {data.down.length}개</summary>{data.down.map(w=><div className="toolbar" key={w.id}><span>{w.title}</span>{data.can_edit&&<button disabled={!!busy} onClick={()=>act(`u${w.id}`,`widgets/${w.id}`,{status:'올림'},'다시 올렸어요.')}>올리기</button>}</div>)}</details>}
   <h2>기록 현황</h2><div className="widget-grid">{data.auto.map(w=><WidgetCard key={w.title} w={w} tid={tid}/>)}</div>
  </>}</>;
}
