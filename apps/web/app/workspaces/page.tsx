import { api } from '../../lib/api';
import { createWorkspace } from '../actions';
export const dynamic='force-dynamic';
export default async function All() {
 const rows:{id:number,title:string,role:string,hits:number|null,review:number|null,records:number|null}[]=await api('/v1/workspaces/summary');
 return <main className="all-spaces"><a href="/">← 홈으로</a><h1>모든 워크스페이스</h1><p className="muted">숫자는 모두 기록에서 셌어요.</p>
  <div className="table-wrap"><table className="plain-table"><thead><tr><th>워크스페이스</th><th>내 역할</th><th>오늘 걸린 것</th><th>확인할 것</th><th>기록</th></tr></thead>
  <tbody>{rows.map(w=><tr key={w.id}><td><a href={`/?workspace=${w.id}&view=home`}><b>{w.title}</b></a></td><td>{w.role}</td><td>{w.hits??'—'}건</td><td>{w.review??'—'}개</td><td>{w.records??'—'}줄</td></tr>)}</tbody></table></div>
  <form action={createWorkspace} className="inline-form"><label>새 워크스페이스 이름<input name="title" maxLength={60} placeholder="예: 2호점 재고"/></label><button className="primary">워크스페이스 생성</button></form></main>;
}
