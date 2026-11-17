import { api } from '../../lib/api';
import { saveMe, logout, deleteAccount } from '../actions';
import { supabase } from '../../lib/supabase';
import { LegalLinks } from '../legal';
export const dynamic='force-dynamic';
type Space={id:number,title:string|null};
const ERRORS:Record<string,string>={
 invalid:'이름, 이메일 모양, 휴대폰 번호를 확인해 주세요.',
 confirm:'지우면 되돌릴 수 없다는 것을 확인해 주세요.',
 owner:'다른 구성원이 있는 워크스페이스는 먼저 owner를 넘겨 주세요.',
 delete:'계정을 지우지 못했어요. 잠시 뒤 다시 해 주세요.',
};
export default async function Account({searchParams}:{searchParams:Promise<{saved?:string,error?:string}>}) {
 const [me,plan]:[{name?:string,email?:string,phone?:string,provider?:string},{workspaces:Space[],blocked:Space[]}]=await Promise.all([api('/v1/me'),api('/v1/me/deletion')]);
 const sb=await supabase();const {data:{user}}=await sb.auth.getUser();const {saved,error}=await searchParams;
 const via:Record<string,string>={email:'이메일',google:'Google',kakao:'카카오'};
 const name=(w:Space)=>w.title||'이름 없는 워크스페이스';
 return <main className="all-spaces account-page"><a href="/">← 홈으로</a><h1>내 계정</h1>
  <p className="muted">로그인: {user?.email||'—'} · {via[me.provider||'']||me.provider}</p>
  {saved&&<p className="success" role="status">저장했어요.</p>}{error&&<p className="error" role="alert">{ERRORS[error]||ERRORS.invalid}</p>}
  <form action={saveMe} className="manual-form"><label>이름<input name="name" required maxLength={60} defaultValue={me.name||''}/></label>
   <label>연락 이메일<input type="email" name="email" maxLength={254} defaultValue={me.email||''}/></label>
   <label>휴대폰 번호<input name="phone" maxLength={30} inputMode="tel" defaultValue={me.phone||''}/></label>
   <button className="primary">저장</button></form>
  <form action={logout}><button>로그아웃</button></form>
  <section className="danger-zone"><h2>계정 지우기</h2>
   {plan.blocked.length?<>
    <p>다른 구성원이 있는 워크스페이스의 owner예요. 먼저 워크스페이스 관리의 구성원 표에서 [owner 넘기기]를 해 주세요.</p>
    <ul>{plan.blocked.map(w=><li key={w.id}><a href={`/?workspace=${w.id}&view=settings`}>{name(w)}</a></li>)}</ul></>
   :<form action={deleteAccount}>
    <p>계정을 지우면 바로 지워지고 되돌릴 수 없어요.</p>
    <ul>
     <li>계정 정보(이름 · 이메일 · 휴대폰 번호)와 로그인 연결</li>
     {plan.workspaces.length>0&&<li>혼자 쓰는 워크스페이스 {plan.workspaces.length}개와 그 안의 기록 · 원본 사진 · 대화: {plan.workspaces.map(name).join(', ')}</li>}
     <li>다른 사람과 함께 쓰는 워크스페이스에 올린 종이와 기록은 그 워크스페이스에 남고, 누가 올렸는지만 지워져요.</li>
    </ul>
    <label className="agree"><input type="checkbox" name="confirm" required/><span>지우면 되돌릴 수 없다는 것을 확인했어요.</span></label>
    <button className="danger">계정 지우기</button></form>}
  </section>
  <LegalLinks/></main>;
}
