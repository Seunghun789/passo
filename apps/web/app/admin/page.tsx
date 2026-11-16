import { notFound } from 'next/navigation';
import { apiResponse } from '../../lib/api';
export const dynamic='force-dynamic';
type Account={name:string|null,email:string|null,stage:number,month_papers:number,last:string|null,cost:number};
type Space={title:string,org:string,owner:string,use:string|null,papers:number,records:number,last:string|null,cost:number};
type O={accounts:Account[],spaces:Space[],funnel:number[],active:number,before:number,mix:Record<string,number>,cells:number,fixed:number,paper_cost:number|null,stages:string[],plan:{name:string,papers:number}};
const seen=(iso:string|null)=>{if(!iso)return '—';const d=Math.floor((Date.now()-new Date(iso).getTime())/864e5);return d<=0?'오늘':d===1?'어제':`${d}일 전`;};
const usd=(n:number)=>'$'+n.toFixed(2);

export default async function Admin({searchParams}:{searchParams:Promise<{view?:string,show?:string,q?:string}>}) {
 const r=await apiResponse('/v1/admin',{},true);
 if(r.status===403) notFound();  // 관리자가 아니면 화면도 숫자도 없다
 if(!r.ok) return <main className="all-spaces"><h1>관리</h1><p className="error">관리 화면을 불러오지 못했어요. 서버 설정을 확인해 주세요.</p></main>;
 const o:O=await r.json();const {view,show,q}=await searchParams;
 if(view==='spaces'){
  const used=o.spaces.filter(w=>w.use);
  const tabs:[string,string,Space[]][]=[['all',`전체 ${o.spaces.length}`,o.spaces],['used',`이번 주 활용 ${used.length}`,used],['idle',`이번 주 없음 ${o.spaces.length-used.length}`,o.spaces.filter(w=>!w.use)]];
  const [key,,list]=tabs.find(t=>t[0]===show)||tabs[0];const word=(q||'').trim().toLowerCase();
  const rows=list.filter(w=>!word||`${w.title} ${w.owner}`.toLowerCase().includes(word));
  return <main className="all-spaces admin"><a href="/admin">← 관리로</a><h1>전체 워크스페이스</h1>
   <div className="toolbar"><div className="segments">{tabs.map(([k,l])=><a key={k} className="button" aria-pressed={k===key} href={`/admin?view=spaces&show=${k}${word?'&q='+encodeURIComponent(word):''}`}>{l}</a>)}</div>
    <form className="inline-form"><input type="hidden" name="view" value="spaces"/><input type="hidden" name="show" value={key}/><input name="q" defaultValue={q||''} placeholder="워크스페이스 · owner 찾기" aria-label="찾기"/><button>찾기</button></form></div>
   {rows.length?<div className="table-wrap"><table className="plain-table"><thead><tr><th>워크스페이스</th><th>owner</th><th>구독 등급</th><th>이번 주 활용</th><th>올린 종이</th><th>기록</th><th>최근 기록</th><th>이번 달 금액</th></tr></thead>
    <tbody>{rows.map((w,i)=><tr key={i}><td><b>{w.title}</b> <small className="muted">{w.org}</small></td><td>{w.owner}</td><td><span className="chip">{o.plan.name}</span></td><td>{w.use?<span className="chip done">{w.use}</span>:<small className="muted">이번 주 없음</small>}</td><td>{w.papers}</td><td>{w.records}</td><td>{seen(w.last)}</td><td>{usd(w.cost)}</td></tr>)}</tbody></table></div>:<p className="muted">찾는 워크스페이스가 없어요.</p>}</main>;
 }
 const total=o.funnel[0]||0,mix=Object.entries(o.mix).map(([k,n])=>`${k} ${n}`).join(', ');
 return <main className="all-spaces admin"><a href="/">← 홈으로</a><h1>관리</h1>
  <a className="panel admin-hero" href="/admin?view=spaces&show=used"><span>이번 주 활용 워크스페이스</span><strong>{o.active}</strong><small className="muted">지난주 {o.before} · {mix}</small><em>전체 워크스페이스 보기</em></a>
  <h2>어디까지 가나</h2><div className="admin-funnel">{o.stages.map((name,i)=>{const n=o.funnel[i]||0,before=i?o.funnel[i-1]:0;
   return <div className="panel" key={name}><span>{name}</span><strong>{n}</strong><div className="bar"><i style={{width:`${total?n/total*100:0}%`}}/></div>
    <small className="muted">{before?`${Math.round(n/before*100)}%`:''}{name==='확인 완료'&&before>n?` · ${before-n}명이 확인에서 멈춤`:''}{name==='재사용'?' · 7~14일 안에 다시 올림':''}</small></div>;})}</div>
  <div className="metrics"><div className="panel metric"><span>고친 값 비율</span><strong>{o.cells?`${Math.round(o.fixed/o.cells*100)}%`:'—'}</strong></div>
   <div className="panel metric"><span>종이 한 장당 AI 비용</span><strong>{o.paper_cost!=null?usd(o.paper_cost):'—'}</strong></div></div>
  <h2>계정</h2><div className="table-wrap"><table className="plain-table"><thead><tr><th>계정</th><th>구독 등급</th><th>이번 달 종이</th><th>도달 단계</th><th>최근 연 날</th><th>이번 달 금액</th></tr></thead>
   <tbody>{o.accounts.map((a,i)=><tr key={i}><td>{a.name||a.email||'—'} <small className="muted">{a.name?a.email:''}</small></td><td><span className="chip">{o.plan.name}</span></td>
    <td>{a.month_papers} / {o.plan.papers}장<div className="bar"><i style={{width:`${Math.min(a.month_papers/o.plan.papers,1)*100}%`,background:a.month_papers>=o.plan.papers*.8?'#D97706':undefined}}/></div></td>
    <td>{o.stages[a.stage]}</td><td>{seen(a.last)}</td><td>{usd(a.cost)}</td></tr>)}</tbody></table></div>
  <p className="muted">구독 등급과 한도는 아직 실제로 막지 않는 예시예요.</p></main>;
}
