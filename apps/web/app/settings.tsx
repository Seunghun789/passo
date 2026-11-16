'use client';
import {useCallback,useEffect,useState} from 'react';
import {useRouter} from 'next/navigation';
type Request=(path:string,init?:RequestInit)=>Promise<any>;
type Info={title:string,about:string|null,org:string|null,industry:string|null,product:string|null,website:string|null,role:string,org_owner:boolean};
type Member={user_id:number,name:string,email:string|null,role:string,me:boolean,last_opened_at:string|null};
type Invite={token:string,role:string,expires_at:string,used_by:string|null,created_at:string};
type Data={info:Info,members:Member[],invites:Invite[],roles:{role:string,can:string[]}[]};
const ROLES=['확인하는 사람','올리는 사람','보는 사람'];
const fail=(e:unknown)=>{const m=(e as Error).message;return m==='요청을 처리하지 못했어요. 다시 시도해 주세요.'?'저장하지 못했어요. 입력을 확인해 주세요.':m;};
const day=(iso:string|null)=>iso?new Intl.DateTimeFormat('ko',{month:'long',day:'numeric',timeZone:'Asia/Seoul'}).format(new Date(iso)):'—';

export default function Settings({request}:{request:Request}){
 const router=useRouter();
 const [data,setData]=useState<Data|null>(null),[tab,setTab]=useState('구성원'),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const [role,setRole]=useState('확인하는 사람'),[inviting,setInviting]=useState(false),[link,setLink]=useState('');
 const load=useCallback(()=>request('settings').then(setData).catch(e=>setError(fail(e))),[request]);
 useEffect(()=>{load();},[load]);
 async function act(path:string,body:object,done:string){setBusy(true);setError('');setNotice('');
  try{const r=await request(path,{method:'POST',body:JSON.stringify(body)});await load();setNotice(done);return r;}catch(e){setError(fail(e));return null;}finally{setBusy(false);}}
 async function save(e:React.FormEvent<HTMLFormElement>){e.preventDefault();const f=new FormData(e.currentTarget);
  if(await act('settings',Object.fromEntries(['title','about','org','industry','product','website'].map(k=>[k,String(f.get(k)||'')])),'저장했어요.'))router.refresh();}  // 사이드바의 워크스페이스 이름도 바꾼다
 if(!data)return <><h1>워크스페이스 관리</h1>{error?<p className="error" role="alert">{error}</p>:<p className="muted">불러오는 중이에요...</p>}</>;
 const owner=data.info.role==='주인',i=data.info;
 return <><h1>워크스페이스 관리</h1><p className="muted">내 역할: {i.role}{owner?'':' · 정보와 구성원은 주인이 바꿔요.'}</p>
  {error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="success" role="status">{notice}</p>}
  <section className="panel settings-block"><h2>워크스페이스 정보</h2>
   <form onSubmit={save} className="pick-form settings-form">
    <label>워크스페이스 이름<input name="title" required maxLength={60} defaultValue={i.title||''} disabled={!owner}/></label>
    <label>하는 일 · 무엇을 기록하나요<input name="about" maxLength={500} defaultValue={i.about||''} disabled={!owner}/></label>
    <label>조직 이름<input name="org" maxLength={100} defaultValue={i.org||''} disabled={!i.org_owner}/></label>
    <label>업종<input name="industry" maxLength={100} defaultValue={i.industry||''} disabled={!i.org_owner}/></label>
    <label>대표 제품 · 서비스<input name="product" maxLength={200} defaultValue={i.product||''} disabled={!i.org_owner}/></label>
    <label>웹사이트<input name="website" maxLength={300} defaultValue={i.website||''} disabled={!i.org_owner}/></label>
    {owner&&<div className="form-actions"><button className="primary" disabled={busy}>변경사항 저장하기</button></div>}</form></section>
  <section className="panel settings-block"><h2>권한 관리</h2><div className="table-wrap"><table className="plain-table"><thead><tr><th>역할</th><th>할 수 있는 일</th></tr></thead>
   <tbody>{data.roles.map(r=><tr key={r.role}><td><b>{r.role}</b></td><td>{r.can.join(' · ')}</td></tr>)}</tbody></table></div></section>
  <section className="panel settings-block"><div className="toolbar"><h2>구성원 관리</h2>{owner&&<button className="primary" onClick={()=>{setInviting(!inviting);setLink('');}}>구성원 초대하기</button>}</div>
   {inviting&&owner&&<div className="invite-box"><label>역할<select value={role} onChange={e=>setRole(e.target.value)}>{ROLES.map(r=><option key={r}>{r}</option>)}</select></label>
    <button className="primary" disabled={busy} onClick={async()=>{const r=await act('invites',{role},'초대 링크를 만들었어요. 7일 동안 쓸 수 있어요.');if(r)setLink(`${location.origin}/invite/${r.token}`);}}>초대</button>
    {link&&<div className="invite-link"><input readOnly value={link} aria-label="초대 링크" onFocus={e=>e.currentTarget.select()}/><button onClick={()=>navigator.clipboard?.writeText(link).then(()=>setNotice('링크를 복사했어요.'))}>복사</button></div>}</div>}
   <div className="tabs" role="tablist">{['구성원',...(owner?['초대 링크']:[])].map(t=><button role="tab" key={t} aria-selected={tab===t} onClick={()=>setTab(t)}>{t==='구성원'?`구성원 ${data.members.length}`:`초대 링크 ${data.invites.length}`}</button>)}</div>
   {tab==='구성원'&&<div className="table-wrap"><table className="plain-table"><thead><tr><th>이름</th><th>이메일</th><th>역할</th><th>마지막으로 연 날</th>{owner&&<th></th>}</tr></thead>
    <tbody>{data.members.map(m=><tr key={m.user_id}><td><b>{m.name||'이름 없음'}</b>{m.me&&<small className="muted"> · 나</small>}</td><td>{m.email||'—'}</td>
     <td>{owner&&m.role!=='주인'?<select aria-label={`${m.name} 역할`} value={m.role} disabled={busy} onChange={e=>act(`members/${m.user_id}`,{role:e.target.value},`${m.name}의 역할을 바꿨어요.`)}>{ROLES.map(r=><option key={r}>{r}</option>)}</select>:m.role}</td>
     <td>{day(m.last_opened_at)}</td>{owner&&<td>{m.role!=='주인'&&<button className="text-button" disabled={busy} onClick={()=>{if(confirm(`${m.name}을(를) 이 워크스페이스에서 내보낼까요? 올린 종이와 기록은 남아요.`))act(`members/${m.user_id}/remove`,{},`${m.name}을(를) 내보냈어요.`);}}>내보내기</button>}</td>}</tr>)}</tbody></table></div>}
   {tab==='초대 링크'&&owner&&<div className="table-wrap"><table className="plain-table"><thead><tr><th>역할</th><th>만든 날</th><th>끝나는 날</th><th>상태</th></tr></thead>
    <tbody>{data.invites.map(v=><tr key={v.token}><td>{v.role}</td><td>{day(v.created_at)}</td><td>{day(v.expires_at)}</td>
     <td>{v.used_by?`${v.used_by} 참여`:new Date(v.expires_at)<new Date()?'기간 지남':<button className="text-button" onClick={()=>{const l=`${location.origin}/invite/${v.token}`;navigator.clipboard?.writeText(l).then(()=>setNotice('링크를 복사했어요.'));}}>링크 복사</button>}</td></tr>)}</tbody></table></div>}
  </section></>;
}
