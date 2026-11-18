'use client';
import {useEffect,useRef,useState} from 'react';
import {createWorkspace} from './actions';
type W={id:number,title:string,role:string,org?:string|null};
const MANAGE:[string,string][]=[['조직 정보','ws-info'],['워크스페이스 정보','ws-info'],['구성원 관리','ws-members'],['권한 관리','ws-roles']];

// 사이드바 맨 위: 워크스페이스 이름과 [+]. 펼치면 검색 · 조직별 목록 · [워크스페이스 생성] · [모두 보기] · "조직 이름 관리"
export default function WorkspacePicker({workspaces,selected,view,go}:{workspaces:W[],selected?:W,view:string,go:(v:string)=>void}){
 const [open,setOpen]=useState(false),[find,setFind]=useState(''),[pos,setPos]=useState({top:0,left:0});
 const button=useRef<HTMLButtonElement>(null),menu=useRef<HTMLDivElement>(null);
 useEffect(()=>{
  if(!open)return;
  const r=button.current?.getBoundingClientRect();if(r)setPos({top:r.bottom+6,left:r.left});
  const close=(e:MouseEvent)=>{const t=e.target as Node;if(!menu.current?.contains(t)&&!button.current?.contains(t))setOpen(false);};
  const esc=(e:KeyboardEvent)=>{if(e.key==='Escape')setOpen(false);};
  document.addEventListener('mousedown',close);document.addEventListener('keydown',esc);
  return()=>{document.removeEventListener('mousedown',close);document.removeEventListener('keydown',esc);};
 },[open]);
 const shown=workspaces.filter(w=>!find||w.title.includes(find)||(w.org||'').includes(find));
 const orgs=[...new Set(shown.map(w=>w.org||'내 조직'))];
 const manage=(id:string)=>{setOpen(false);history.replaceState(null,'',`#${id}`);go('settings');};
 return <>
  <div className="ws-row">
   <button ref={button} type="button" className="ws-pick" aria-haspopup="menu" aria-expanded={open} onClick={()=>setOpen(!open)}><span>{selected?.title||'워크스페이스 고르기'}</span><span aria-hidden="true">⌄</span></button>
   <form action={createWorkspace} className="ws-plus"><input type="hidden" name="title" value="새 워크스페이스"/><button type="submit" title="워크스페이스 생성" aria-label="워크스페이스 생성">+</button></form>
  </div>
  {open&&<div ref={menu} className="ws-menu" style={{top:pos.top,left:pos.left}} role="menu" aria-label="워크스페이스">
   <input className="ws-find" aria-label="나의 워크스페이스 검색" placeholder="나의 워크스페이스 검색" value={find} onChange={e=>setFind(e.target.value)} autoFocus/>
   {orgs.map(o=><div key={o}><p className="ws-org">{o}</p>
    {shown.filter(w=>(w.org||'내 조직')===o).map(w=><a key={w.id} role="menuitem" className="ws-item" href={`/?workspace=${w.id}&view=${view}`} aria-current={w.id===selected?.id?'true':undefined}><span>{w.title}</span>{w.id===selected?.id&&<span className="ws-check" aria-label="지금 워크스페이스">✓</span>}</a>)}</div>)}
   {!shown.length&&<p className="ws-org">찾는 워크스페이스가 없어요.</p>}
   <form action={createWorkspace}><input type="hidden" name="title" value="새 워크스페이스"/><button type="submit" className="ws-new">워크스페이스 생성</button></form>
   {workspaces.length>1&&<a role="menuitem" className="ws-item ws-all" href="/workspaces">모두 보기</a>}
   {selected&&<><p className="ws-head">{selected.org||'이 조직'} 관리</p>
    {MANAGE.map(([label,id])=><button key={label} type="button" role="menuitem" className="ws-item" onClick={()=>manage(id)}>{label}</button>)}</>}
  </div>}
 </>;
}
