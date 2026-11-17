'use client';
import {Fragment,useCallback,useEffect,useRef,useState} from 'react';
type Request=(path:string,init?:RequestInit)=>Promise<any>;
type Table={columns:string[],rows:{id:number,source_id?:number|null,values:Record<string,unknown>}[],total:number};
type Alert={id:number,title:string,type:string,rule:string,chip:string,kind:string,count:number,until:string,headline?:string|null,targets?:{name:string,why:string}[],follow?:{name:string,why:string}[],evidence?:Table};
type Suggestion={source?:string,id?:number,title:string,type:string,rule:string,reason?:string,count:number,backtest:number,chip:string,schedule?:{text:string,hit:number,of:number}|null,evidence:Table};
type Glance={title:string,value:string,previous:string,previous_label:string,evidence:number};
type HomeData={enabled:number,alerts:Alert[],more:{title:string,count:number}[],quiet:string[],glance:Glance[]};
type CalEvent={id:number,time:string,name:string,side:string,color:string};
type CalDay={iso:string,n:number,wd:number,wdk:string,today:boolean,past:boolean,out:boolean,events:CalEvent[]};
type View={id?:number,source?:string,shape?:string,type?:string,title:string,kind:'number'|'vega'|'table'|'status'|'list'|'calendar'|'empty',until:string,reason?:string|null,evidence:Table,
 value?:string,previous?:string,previous_label?:string,rule?:string,vega?:Record<string,unknown>,columns?:string[],rows?:Record<string,unknown>[],
 items?:{id?:number,label?:string,value?:string,names?:string[],at?:string,name?:string,side?:string,color?:string}[],more?:number,prop?:string,
 mode?:'week'|'month',offset?:number,label?:string,heads?:string[],days?:CalDay[],legend?:{name:string,color:string}[],message?:string,
 write?:{type:string,prop:string,fields:{name:string,dtype:string,unit:string|null}[]}};
type PickOption={type:string,numbers:string[],groups:string[],dates:string[],values:Record<string,string[]>};
type ChatRow={id:number,title:string,made:boolean,updated_at:string,deleted_at:string|null,days_left:number|null};
type ChatMsg={index:number,role:'user'|'assistant',text:string,done:boolean,title?:string,preview?:View|Suggestion,stale?:string};
type Chat={id:number,title:string,messages:ChatMsg[],chips:string[]};
const PERIODS=['오늘','이번 주','이번 달','올해'];
const show=(v:unknown)=>v===null||v===undefined||v===''?'—':typeof v==='object'?JSON.stringify(v):String(v);
const fail=(e:unknown)=>{const m=(e as Error).message;return m==='요청을 처리하지 못했어요. 다시 시도해 주세요.'?'잠시 뒤 다시 눌러 주세요.':m;};

export function Evidence({table,tid,label}:{table:Table,tid:number,label?:string}){
 const [open,setOpen]=useState<number|null>(null),[shown,setShown]=useState(false);  // 표는 펼칠 때 그린다. 카드가 수백 장이라 닫힌 표까지 그리면 화면이 무겁다
 if(!table.total)return null;
 return <details className="proof" onToggle={e=>setShown(e.currentTarget.open)}><summary>{label||`근거 기록 ${table.total}줄`}</summary>
  {shown&&<><div className="table-wrap"><table className="plain-table"><thead><tr>{table.columns.map(c=><th key={c}>{c}</th>)}</tr></thead>
  <tbody>{table.rows.map(r=><Fragment key={r.id}><tr className={r.source_id?'clickable':''} onClick={()=>r.source_id&&setOpen(open===r.id?null:r.id)}>{table.columns.map(c=><td key={c}>{show(r.values[c])}</td>)}</tr>
   {open===r.id&&r.source_id&&<tr><td colSpan={table.columns.length}><img className="evidence-photo" src={`/api/workspaces/${tid}/business/sources/${r.source_id}/original?page=1`} alt="원본 사진"/></td></tr>}</Fragment>)}</tbody></table></div>
  {table.total>table.rows.length&&<p className="muted">앞의 {table.rows.length}줄만 보여요.</p>}</>}</details>;
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


function Vega({spec,title}:{spec:Record<string,unknown>,title:string}){
 const ref=useRef<HTMLDivElement>(null),[failed,setFailed]=useState(false);
 useEffect(()=>{let alive=true,finalize:(()=>void)|null=null;
  import('vega-embed').then(({default:embed})=>{if(!alive||!ref.current)return;
   return embed(ref.current,{...spec,width:'container',autosize:{type:'fit-x',contains:'padding'}} as never,{actions:false,renderer:'svg'}).then(r=>{if(alive)finalize=()=>r.finalize();else r.finalize();});
  }).catch(()=>alive&&setFailed(true));
  return()=>{alive=false;finalize?.();};},[spec]);
 return failed?<p className="muted">그림을 그리지 못했어요.</p>:<div className="vega" ref={ref} role="img" aria-label={title}/>;
}

function CalendarWrite({w,day,request,onSaved,onClose}:{w:NonNullable<View['write']>,day:string,request:Request,onSaved:()=>void,onClose:()=>void}){
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),key=useRef(crypto.randomUUID());
 const d=new Date(day+'T00:00:00'),label=`${d.getMonth()+1}월 ${d.getDate()}일 ${'일월화수목금토'[d.getDay()]}요일 · 직접 적기`;
 async function save(e:React.FormEvent<HTMLFormElement>){e.preventDefault();setBusy(true);setError('');const f=new FormData(e.currentTarget),data:Record<string,string|number|null>={};
  for(const x of w.fields){const v=String(f.get(x.name)??'').trim();if(v)data[x.name]=x.dtype==='number'&&Number.isFinite(Number(v))?Number(v):v;}
  const at=String(f.get('__at')||day),tm=String(f.get('__time')||'');data[w.prop]=tm?`${at} ${tm}`:at;
  try{await request('manual-records',{method:'POST',body:JSON.stringify({request_key:key.current,type_name:w.type,occurred_at:new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Seoul'}),data})});onSaved();}
  catch(err){setError((err as Error).message);}finally{setBusy(false);}}
 return <form className="panel cal-pick cal-write" onSubmit={save}><div className="toolbar"><b>{label}</b><button type="button" className="text-button" onClick={onClose}>닫기</button></div>
  <p className="muted">{w.type} 칸 그대로 적어요. {w.prop} 날짜는 채워 뒀어요.</p>
  <div className="pick-form"><label>{w.prop}<input type="date" name="__at" defaultValue={day}/></label><label>시각<input type="time" name="__time" step={1800}/></label>
   {w.fields.map(x=><label key={x.name}>{x.name}{x.unit?` (${x.unit})`:''}<input name={x.name} type={x.dtype==='date'?'date':'text'} inputMode={x.dtype==='number'?'decimal':undefined} maxLength={1000}/></label>)}</div>
  {error&&<p className="error" role="alert">{error}</p>}<button className="primary" disabled={busy}>{busy?'저장 중…':'저장'}</button></form>;
}

function Calendar({v,tid,request,wid}:{v:View,tid:number,request:Request,wid?:number}){
 const [cal,setCal]=useState(v),[pick,setPick]=useState<number|null>(null),[blank,setBlank]=useState<string|null>(null),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 useEffect(()=>{setCal(v);setPick(null);setBlank(null);},[v]);
 async function reload(step:number){setBusy(true);try{setCal(await request(`widgets/${wid}/calendar?mode=${cal.mode}&offset=${(cal.offset||0)+step}`));}finally{setBusy(false);}}
 async function move(step:number){if(!wid)return;await reload(step);setPick(null);setBlank(null);}
 const row=pick===null?null:cal.evidence.rows.find(r=>r.id===pick);
 const [back,next]=cal.mode==='week'?['지난주','다음 주']:['지난달','다음 달'];
 return <div className={`calendar ${cal.mode}`}>
  <div className="toolbar cal-head"><b>{cal.label}</b>{wid&&<div className="cal-nav"><button disabled={busy} onClick={()=>move(-1)}>{back}</button><button disabled={busy} onClick={()=>move(1)}>{next}</button></div>}</div>
  {notice&&<p className="success" role="status">{notice}</p>}
  <div className="cal-grid">{cal.mode==='month'&&cal.heads?.map(h=><div key={h} className={`cal-hd${h==='일'?' sun':''}`}>{h}</div>)}
   {cal.days?.map(d=><div key={d.iso} className={`cal-day${d.out?' out':''}${d.today?' today':''}${d.past?' past':''}${d.wd===0?' sun':''}${blank===d.iso?' on':''}`}
     onClick={e=>{if(wid&&cal.write&&e.target===e.currentTarget){setBlank(d.iso);setPick(null);setNotice('');}}}>
    <div className="cal-n">{cal.mode==='week'?`${d.n} ${d.wdk}${d.today?' · 오늘':''}`:d.n}</div>
    {d.events.map(e=><button key={e.id} className={`cal-ev${pick===e.id?' on':''}`} style={{borderLeftColor:e.color}} onClick={()=>{setPick(pick===e.id?null:e.id);setBlank(null);}}>{e.time&&<small>{e.time}</small>}<span>{e.name}</span>{e.side&&<small>{e.side}</small>}</button>)}
   </div>)}</div>
  {!!cal.legend?.length&&<div className="cal-legend">{cal.legend.map(l=><span key={l.name}><i style={{background:l.color}}/>{l.name}</span>)}</div>}
  {wid&&cal.write&&<p className="muted">빈 곳을 누르면 그 날짜로 직접 적을 수 있어요.</p>}
  {row&&<div className="panel cal-pick"><div className="toolbar"><b>{show(row.values[Object.keys(row.values)[0]])}</b><button onClick={()=>setPick(null)}>닫기</button></div>
   <dl>{Object.entries(row.values).map(([k,x])=><Fragment key={k}><dt>{k}</dt><dd>{show(x)}</dd></Fragment>)}</dl>
   {row.source_id&&<img className="evidence-photo" src={`/api/workspaces/${tid}/business/sources/${row.source_id}/original?page=1`} alt="원본 사진"/>}</div>}
  {blank&&cal.write&&<CalendarWrite w={cal.write} day={blank} request={request} onClose={()=>setBlank(null)} onSaved={async()=>{setBlank(null);await reload(0);setNotice('저장했어요. 달력에 보여요.');}}/>}
 </div>;
}

function ViewBody({v,tid,request,wid}:{v:View,tid:number,request:Request,wid?:number}){
 if(v.kind==='number')return <><strong className="big-number">{v.value}</strong><p className="muted until">{v.previous_label} {v.previous}{v.rule?` · ${v.rule}`:''}</p></>;
 if(v.kind==='vega'&&v.vega)return <Vega spec={v.vega} title={v.title}/>;
 if(v.kind==='table')return <div className="table-wrap"><table className="plain-table"><thead><tr>{v.columns?.map(c=><th key={c}>{c}</th>)}</tr></thead><tbody>{v.rows?.map((r,i)=><tr key={i}>{v.columns?.map(c=><td key={c}>{show(r[c])}</td>)}</tr>)}</tbody></table></div>;
 if(v.kind==='status')return <div className="status-grid">{v.items?.map(x=><div className="panel" key={x.label}><span>{x.label}</span><strong>{x.value}</strong>{!!x.names?.length&&<small className="muted">{x.names.join(', ')}</small>}</div>)}</div>;
 if(v.kind==='list')return v.items?.length?<><ul className="upcoming">{v.items.map(x=><li key={x.id}><i style={{background:x.color}}/><span className="muted">{x.at}</span><b>{x.name}</b><small className="muted">{x.side}</small></li>)}</ul>{!!v.more&&<small className="muted">그 뒤 {v.more}건 더</small>}</>:<p className="muted">오늘부터 적힌 {v.prop}이(가) 없어요.</p>;
 if(v.kind==='calendar')return <Calendar v={v} tid={tid} request={request} wid={wid}/>;
 return <p className="muted">{v.message}</p>;
}

function ViewCard({v,tid,request,action,wid}:{v:View,tid:number,request:Request,action?:React.ReactNode,wid?:number}){
 return <article className="panel widget"><div className="toolbar"><b>{v.title}</b>{action}</div>
  <ViewBody v={v} tid={tid} request={request} wid={wid}/><p className="muted until">{v.until}</p>
  {v.reason&&<p className="muted">{v.reason}</p>}
  <Evidence table={v.evidence} tid={tid}/></article>;
}

function SuggestionCard({s,tid,actions}:{s:Suggestion,tid:number,actions?:React.ReactNode}){
 return <article className="panel suggestion">
  <div className="alert-head"><span className="tag">{s.chip}</span><b>{s.title}</b>{s.source==='proposal'&&<span className="muted">AI 추천</span>}</div><p className="muted">{s.rule}</p>{s.reason&&<p>{s.reason}</p>}
  {s.schedule&&<p className="muted">최근 {s.schedule.of}번 중 {s.schedule.hit}번이 {s.schedule.text}</p>}
  <p>지금 걸린 것 {s.count}건 · 지난 30일이었다면 {s.backtest}번 걸렸어요 (근거 {s.backtest}줄)</p>
  <Evidence table={s.evidence} tid={tid} label={`지금 걸린 기록 ${s.evidence.total}줄`}/>
  {actions&&<div className="card-actions">{actions}</div>}
  <small className="muted">알림을 보내거나 기록을 바꾸지는 않아요.</small></article>;
}

const SHOWN=6;  // 추천은 걸린 것 · 값이 있는 것부터 몇 장만 펼치고, 나머지는 접어 둔다
const quiet=(v:{kind?:string,value?:string,count?:number})=>v.kind==='empty'||v.value==='0'||v.count===0;
function Fold<T>({items,label,render}:{items:T[],label:string,render:(x:T,i:number)=>React.ReactNode}){
 return <>{items.slice(0,SHOWN).map(render)}
  {items.length>SHOWN&&<details className="paper-group fold"><summary>{label} {items.length-SHOWN}개 더</summary><div className="fold-body">{items.slice(SHOWN).map((x,i)=>render(x,i+SHOWN))}</div></details>}</>;
}

function useAct(request:Request,load:()=>Promise<unknown>,setError:(e:string)=>void){
 const [busy,setBusy]=useState(''),[notice,setNotice]=useState('');
 const act=async(key:string,path:string,body:object,done:string)=>{setBusy(key);setNotice('');setError('');
  try{await request(path,{method:'POST',body:JSON.stringify(body)});await load();setNotice(done);return true;}catch(e){setError(fail(e));return false;}finally{setBusy('');}};
 return {busy,notice,setNotice,act};
}

const dayGroup=(iso:string)=>{const d=new Date(iso),now=new Date(),start=new Date(now.getFullYear(),now.getMonth(),now.getDate()).getTime(),t=d.getTime();
 return t>=start?'오늘':t>=start-864e5?'어제':t>=start-6*864e5?'지난 7일':'그 전';};

function ChatPanel({request,tid,kind,canEdit,period,onAdopted}:{request:Request,tid:number,kind:'지표'|'업무',canEdit:boolean,period:string,onAdopted:()=>void}){
 const [rows,setRows]=useState<ChatRow[]>([]),[chat,setChat]=useState<Chat|null>(null),[text,setText]=useState(''),[q,setQ]=useState('');
 const [busy,setBusy]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState(''),[dropped,setDropped]=useState<number|null>(null),[renaming,setRenaming]=useState(false),[name,setName]=useState('');
 const list=useCallback(()=>request(`chats?kind=${encodeURIComponent(kind)}`).then(setRows).catch(e=>setError(fail(e))),[request,kind]);
 useEffect(()=>{if(canEdit)list();},[list,canEdit]);
 if(!canEdit)return <p className="info">말로 만들기는 확인하는 사람 이상만 쓸 수 있어요.</p>;
 const open=async(id:number)=>{setError('');setNotice('');setRenaming(false);try{setChat(await request(`chats/${id}?kind=${encodeURIComponent(kind)}&period=${encodeURIComponent(period)}`));}catch(e){setError(fail(e));}};
 async function send(say:string){const r=say.trim();if(!r)return;setBusy('send');setError('');setNotice('');
  try{const c:Chat=await request(`chats?period=${encodeURIComponent(period)}`,{method:'POST',body:JSON.stringify({kind,request:r,...(chat?{chat_id:chat.id}:{})})});setChat(c);setText('');list();}
  catch(e){setError(fail(e));}finally{setBusy('');}}
 async function action(id:number,act:'rename'|'drop'|'restore',title?:string){setBusy(act);setError('');
  try{await request(`chats/${id}`,{method:'POST',body:JSON.stringify({action:act,...(title!==undefined?{title}:{})})});
   if(act==='drop'){setDropped(id);if(chat?.id===id)setChat(null);setNotice('대화를 지웠어요.');}
   if(act==='restore'){setDropped(null);setNotice('대화를 되돌렸어요.');await open(id);}
   if(act==='rename'){setRenaming(false);if(chat)setChat({...chat,title:title||chat.title});}
   await list();}catch(e){setError(fail(e));}finally{setBusy('');}}
 async function adopt(m:ChatMsg){if(!chat||!m.title)return;setBusy(`a${m.index}`);setError('');
  try{await request(kind==='지표'?'widgets':'automations',{method:'POST',body:JSON.stringify({title:m.title,source:'chat',chat_id:chat.id,index:m.index})});
   setNotice(kind==='지표'?'대시보드에 올렸어요.':'켰어요. 홈에 보여요.');await open(chat.id);await list();onAdopted();}
  catch(e){setError(fail(e));}finally{setBusy('');}}
 const live=rows.filter(r=>!r.deleted_at&&(!q||r.title.includes(q))),gone=rows.filter(r=>r.deleted_at);
 const groups=['오늘','어제','지난 7일','그 전'].map(g=>[g,live.filter(r=>dayGroup(r.updated_at)===g)] as const).filter(([,x])=>x.length);
 const yes=kind==='지표'?'올리기':'켜기';
 return <div className="chat">
  <aside className="chat-list"><button className="primary" onClick={()=>{setChat(null);setNotice('');setError('');}}>새 대화</button>
   <input aria-label="대화 검색" placeholder="대화 검색" value={q} onChange={e=>setQ(e.target.value)}/>
   {groups.map(([g,items])=><div key={g}><p className="nav-heading">{g}</p>{items.map(r=><button key={r.id} className={chat?.id===r.id?'active':''} onClick={()=>open(r.id)}>{r.title}{r.made&&<span className="chip done">{kind==='지표'?'올림':'켬'}</span>}</button>)}</div>)}
   {!live.length&&<p className="muted">아직 대화가 없어요.</p>}
   {!!gone.length&&<details><summary>지운 대화 {gone.length}</summary>{gone.map(r=><div key={r.id} className="toolbar"><small>{r.title} · {r.days_left}일 뒤 사라져요</small><button disabled={!!busy} onClick={()=>action(r.id,'restore')}>되돌리기</button></div>)}</details>}
  </aside>
  <section className="chat-main">
   {error&&<p className="error" role="alert">{error}</p>}
   {notice&&<p className="success" role="status">{notice}{dropped&&notice==='대화를 지웠어요.'&&<button className="text-button" onClick={()=>action(dropped,'restore')}>되돌리기</button>}</p>}
   {chat&&<div className="toolbar">{renaming?<form className="rename" onSubmit={e=>{e.preventDefault();action(chat.id,'rename',name);}}><input aria-label="대화 이름" value={name} maxLength={100} onChange={e=>setName(e.target.value)}/><button className="primary" disabled={!!busy}>저장</button></form>:<b>{chat.title}</b>}
    <div className="cal-nav"><button onClick={()=>{setRenaming(!renaming);setName(chat.title);}}>이름 바꾸기</button><button disabled={!!busy} onClick={()=>action(chat.id,'drop')}>지우기</button></div></div>}
   <p className="muted">말로 만들기. 고칠 점은 이어서 말하면 돼요.</p>
   {chat?.messages.map(m=><div key={m.index} className={`msg ${m.role}`}><p>{m.text}</p>
    {m.stale&&<p className="muted">{m.stale}</p>}
    {m.preview&&(kind==='지표'?<ViewCard v={m.preview as View} tid={tid} request={request}/>:<SuggestionCard s={m.preview as Suggestion} tid={tid}/>)}
    {m.preview&&(m.done?<p className="muted">{kind==='지표'?'대시보드에 올렸어요.':'켰어요. 홈에 보여요.'}</p>:<div className="card-actions"><button className="primary" disabled={!!busy} onClick={()=>adopt(m)}>{yes}</button></div>)}
   </div>)}
   {!!chat?.chips.length&&<div className="ask-examples">{chat.chips.map(c=><button key={c} disabled={!!busy} onClick={()=>send(c)}>{c}</button>)}</div>}
   <form className="chat-form" onSubmit={e=>{e.preventDefault();send(text);}}>
    <input aria-label="말로 만들기" value={text} maxLength={500} onChange={e=>setText(e.target.value)} placeholder={kind==='지표'?'예: 일일 합격률 추이를 선 그래프로 / 미팅 예약 달력':'예: 진동이 7을 넘으면 먼저 볼 것에 올려 줘'}/>
    <button className="primary" disabled={!!busy}>{busy==='send'?'확정한 기록으로 만드는 중이에요...':'보내기'}</button></form>
  </section></div>;
}

export function Automation({request,tid,go}:{request:Request,tid:number,go:(v:string)=>void}){
 const {data,error,setError,load}=useLoad<{can_edit:boolean,has_records:boolean,enabled:Alert[],off:{id:number,title:string}[],suggestions:Suggestion[]}>(request,'automations');
 const {busy,notice,act}=useAct(request,load,setError);
 return <><div className="toolbar"><h1>자동화</h1>{data?.can_edit&&data.has_records&&<button disabled={!!busy} onClick={()=>act('rec','automations/recommend',{},'새 제안을 올렸어요.')}>{busy==='rec'?'AI가 기록을 보는 중이에요...':'새로 추천받기'}</button>}</div>
  <p className="muted">켜 둔 자동화는 홈의 &apos;오늘 먼저 볼 것&apos;에 보여요.</p>
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="success" role="status">{notice}</p>}
  {!data&&!error&&<p className="muted">불러오는 중이에요...</p>}
  {data&&!data.has_records&&<div className="empty"><h2>아직 확정한 기록이 없어요.</h2><button className="primary" onClick={()=>go('upload')}>올리기</button></div>}
  {data?.has_records&&<>
   {!!data.suggestions.length&&<><h2>반복 업무 제안</h2><Fold label="반복 업무 제안" items={[...data.suggestions].sort((a,b)=>Number(quiet(a))-Number(quiet(b))||b.backtest-a.backtest)} render={(s,i)=><SuggestionCard key={`${s.source}-${s.id??''}-${s.title}-${i}`} s={s} tid={tid} actions={data.can_edit&&<>
    {s.source==='proposal'&&s.id&&<button disabled={!!busy} onClick={()=>act(`l${s.id}`,`rule-proposals/${s.id}`,{ok:false},'나중에 볼게요.')}>나중에</button>}
    <button className="primary" disabled={!!busy} onClick={()=>act(s.title,'automations',{title:s.title,source:s.source||'rule'},'켰어요. 홈에도 보여요.')}>켜기</button></>}/>}/></>}
   <h2>켜 둔 자동화</h2>{data.enabled.map(a=><article className="panel" key={a.id}><div className="toolbar"><div><b>{a.title}</b>, 지금 {a.count}건<p className="muted">{a.rule}</p></div>
    {data.can_edit&&<button disabled={!!busy} onClick={()=>act(`off${a.id}`,`automations/${a.id}`,{status:'꺼짐'},'껐어요. 홈에서 빠져요.')}>끄기</button>}</div>
    {a.evidence&&<Evidence table={a.evidence} tid={tid} label={`걸린 기록 ${a.count}줄`}/>}</article>)}
   {!data.enabled.length&&<p className="muted">켜 둔 자동화가 없어요.</p>}
   {!!data.off.length&&<details className="paper-group"><summary>꺼 둔 자동화 {data.off.length}개</summary>{data.off.map(a=><div className="toolbar" key={a.id}><span>{a.title}</span>{data.can_edit&&<button disabled={!!busy} onClick={()=>act(`on${a.id}`,`automations/${a.id}`,{status:'켜짐'},'다시 켰어요. 홈에 보여요.')}>다시 켜기</button>}</div>)}</details>}
   <h2>말로 만들기</h2><ChatPanel request={request} tid={tid} kind="업무" canEdit={data.can_edit} period="이번 주" onAdopted={load}/>
  </>}</>;
}

const SHAPES=['숫자 하나','막대','선','표','상태별','달력','목록'];
const FNS:[string,string][]=[['count','건수'],['sum','합계'],['avg','평균'],['max','가장 큰 값'],['min','가장 작은 값']];

function PickBuilder({request,tid,options,period,canEdit,onAdopted}:{request:Request,tid:number,options:PickOption[],period:string,canEdit:boolean,onAdopted:()=>void}){
 const [type,setType]=useState(options[0]?.type||''),[fn,setFn]=useState('count'),[prop,setProp]=useState(''),[by,setBy]=useState(''),[shape,setShape]=useState('막대'),[col,setCol]=useState(''),[val,setVal]=useState('');
 const [out,setOut]=useState<{title:string,shapes:{shape:string,why:string|null}[],view:View|null,message?:string,how?:string}|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 const o=options.find(x=>x.type===type);
 const pick=useCallback(()=>({type,shape,fn,prop:fn==='count'?null:prop||null,by:by||null,conditions:col&&val?[{prop:col,op:'=',value:val}]:[]}),[type,shape,fn,prop,by,col,val]);
 useEffect(()=>{if(!type)return;let alive=true;const t=setTimeout(()=>{request(`widgets/preview?period=${encodeURIComponent(period)}`,{method:'POST',body:JSON.stringify({pick:pick()})}).then(r=>{if(alive){setOut(r);setError('');}}).catch(e=>alive&&setError(fail(e)));},250);return()=>{alive=false;clearTimeout(t);};},[request,pick,period,type]);
 async function put(){if(!out)return;setBusy(true);setError('');try{await request('widgets',{method:'POST',body:JSON.stringify({title:out.title,source:'pick',pick:pick()})});setNotice('올렸어요. "올린 지표"에 보여요.');onAdopted();}catch(e){setError(fail(e));}finally{setBusy(false);}}
 if(!o)return <p className="muted">확정한 기록 종류가 없어요.</p>;
 return <div className="pick"><div className="pick-form">
  <label>기록 종류<select value={type} onChange={e=>{setType(e.target.value);setProp('');setBy('');setCol('');setVal('');}}>{options.map(x=><option key={x.type}>{x.type}</option>)}</select></label>
  <label>셀 방법<select value={fn} onChange={e=>setFn(e.target.value)}>{FNS.map(([k,l])=><option key={k} value={k} disabled={k!=='count'&&!o.numbers.length}>{l}</option>)}</select></label>
  {fn!=='count'&&<label>칸<select value={prop} onChange={e=>setProp(e.target.value)}><option value="">고르세요</option>{o.numbers.map(n=><option key={n}>{n}</option>)}</select></label>}
  <label>나눌 칸<select value={by} onChange={e=>setBy(e.target.value)}><option value="">나누지 않음</option>{[...o.groups,...o.dates].filter((x,i,a)=>a.indexOf(x)===i).map(n=><option key={n}>{n}</option>)}</select></label>
  <label>고를 기록<select value={col} onChange={e=>{setCol(e.target.value);setVal('');}}><option value="">모두</option>{Object.keys(o.values).map(n=><option key={n}>{n}</option>)}</select></label>
  {col&&<label>값<select value={val} onChange={e=>setVal(e.target.value)}><option value="">고르세요</option>{o.values[col]?.map(v=><option key={v}>{v}</option>)}</select></label>}
 </div>
 <div className="segments shapes" aria-label="모양">{SHAPES.map(s=>{const w=out?.shapes.find(x=>x.shape===s);return <button key={s} aria-pressed={shape===s} title={w?.why?`${w.why} 그릴 수 있어요`:''} onClick={()=>setShape(s)}>{s}</button>;})}</div>
 {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="success" role="status">{notice}</p>}
 {out&&(out.view?<><p className="muted">이렇게 셌어요: {out.how}</p><ViewCard v={out.view} tid={tid} request={request} action={canEdit&&<button className="primary" disabled={busy} onClick={put}>올리기</button>}/></>:<p className="info">{out.message}</p>)}
 </div>;
}

export function Dashboard({request,tid,go}:{request:Request,tid:number,go:(v:string)=>void}){
 const [period,setPeriod]=useState('이번 주'),[make,setMake]=useState(''),[shapeOnly,setShapeOnly]=useState('전체');
 const {data,error,setError,load}=useLoad<{can_edit:boolean,has_records:boolean,auto:View[],widgets:View[],down:{id:number,title:string}[],suggestions:View[],gallery:View[],gallery_missing:{shape:string,why:string}[],pick_options:PickOption[]}>(request,`dashboard?period=${encodeURIComponent(period)}`);
 const {busy,notice,act}=useAct(request,load,setError);
 const shapes=['전체',...new Set((data?.gallery||[]).map(v=>v.shape||''))];
 return <><div className="toolbar"><h1>대시보드</h1>{data?.has_records&&<div className="cal-nav">{data.can_edit&&<button disabled={!!busy} onClick={()=>act('rec','widgets/recommend',{},'새 추천 지표를 올렸어요.')}>{busy==='rec'?'AI가 기록을 보는 중이에요...':'새로 추천받기'}</button>}<button className="primary" aria-pressed={!!make} onClick={()=>setMake(make?'':'보기 고르기')}>만들기</button></div>}</div>
  <p className="muted">확정한 기록으로 저절로 그려요. 숫자는 모두 기록에서 셌어요.</p>
  <Periods period={period} set={setPeriod}/>
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="success" role="status">{notice}</p>}
  {!data&&!error&&<p className="muted">불러오는 중이에요...</p>}
  {data&&!data.has_records&&<div className="empty"><h2>아직 확정한 기록이 없어요.</h2><button className="primary" onClick={()=>go('upload')}>올리기</button></div>}
  {data?.has_records&&<>
   {make&&<section className="panel make"><div className="tabs" role="tablist">{['보기 고르기','골라서 만들기','말로 만들기'].map(t=><button role="tab" key={t} aria-selected={make===t} onClick={()=>setMake(t)}>{t}</button>)}</div>
    {make==='보기 고르기'&&<><p className="muted">확정한 칸으로 그릴 수 있는 보기를 내 기록으로 미리 그렸어요. [올리기]를 누른 것만 대시보드에 들어가요.</p>
     <div className="segments">{shapes.map(s=><button key={s} aria-pressed={shapeOnly===s} onClick={()=>setShapeOnly(s)}>{s}</button>)}</div>
     <div className="widget-grid">{data.gallery.filter(v=>shapeOnly==='전체'||v.shape===shapeOnly).map(v=><ViewCard key={v.title} v={v} tid={tid} request={request} action={data.can_edit&&<button className="primary" disabled={!!busy} onClick={()=>act(v.title,'widgets',{title:v.title,source:'gallery'},'올렸어요.')}>올리기</button>}/>)}</div>
     {!data.gallery.length&&<p className="info">지금 칸으로 그릴 수 있는 보기는 모두 올렸어요. [골라서 만들기]나 [말로 만들기]로 더 만들 수 있어요.</p>}
     {data.gallery_missing.map(m=><p key={m.shape} className="muted">{m.shape}: {m.why}</p>)}</>}
    {make==='골라서 만들기'&&<PickBuilder request={request} tid={tid} options={data.pick_options} period={period} canEdit={data.can_edit} onAdopted={load}/>}
    {make==='말로 만들기'&&<ChatPanel request={request} tid={tid} kind="지표" canEdit={data.can_edit} period={period} onAdopted={load}/>}
   </section>}
   <h2>올린 지표</h2>{data.widgets.length?<div className="widget-grid">{data.widgets.map(w=><ViewCard key={w.id} v={w} tid={tid} request={request} wid={w.id} action={data.can_edit&&<button disabled={!!busy} onClick={()=>act(`d${w.id}`,`widgets/${w.id}`,{status:'내림'},'대시보드에서 내렸어요.')}>내리기</button>}/>)}</div>:<p className="muted">올린 지표가 없어요. [만들기]로 보기를 골라 올릴 수 있어요.</p>}
   {!!data.down.length&&<details className="paper-group"><summary>내린 지표 {data.down.length}개</summary>{data.down.map(w=><div className="toolbar" key={w.id}><span>{w.title}</span>{data.can_edit&&<button disabled={!!busy} onClick={()=>act(`u${w.id}`,`widgets/${w.id}`,{status:'올림'},'다시 올렸어요.')}>올리기</button>}</div>)}</details>}
   {!!data.suggestions.length&&<><h2>추천 지표</h2><div className="widget-grid"><Fold label="추천 지표" items={[...data.suggestions].sort((a,b)=>Number(quiet(a))-Number(quiet(b)))} render={(w,i)=><ViewCard key={`${w.source||''}-${w.id??''}-${w.title}-${i}`} v={w} tid={tid} request={request} action={data.can_edit&&<div className="cal-nav">
    {w.source==='proposal'&&w.id&&<button disabled={!!busy} onClick={()=>act(`l${w.id}`,`rule-proposals/${w.id}`,{ok:false},'나중에 볼게요.')}>나중에</button>}
    <button className="primary" disabled={!!busy} onClick={()=>act(w.title,'widgets',{title:w.title,source:w.source||'rule'},'올렸어요.')}>올리기</button></div>}/>}/></div></>}
   <h2>기록 현황</h2><div className="widget-grid">{data.auto.map(w=><ViewCard key={w.title} v={w} tid={tid} request={request}/>)}</div>
  </>}</>;
}
