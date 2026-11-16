import { api } from '../../lib/api';
import { saveMe, logout } from '../actions';
import { supabase } from '../../lib/supabase';
export const dynamic='force-dynamic';
export default async function Account({searchParams}:{searchParams:Promise<{saved?:string,error?:string}>}) {
 const me:{name?:string,email?:string,phone?:string,provider?:string}=await api('/v1/me');
 const sb=await supabase();const {data:{user}}=await sb.auth.getUser();const {saved,error}=await searchParams;
 const via:Record<string,string>={email:'이메일',google:'Google',kakao:'카카오'};
 return <main className="all-spaces account-page"><a href="/">← 홈으로</a><h1>내 계정</h1>
  <p className="muted">로그인: {user?.email||'—'} · {via[me.provider||'']||me.provider}</p>
  {saved&&<p className="success" role="status">저장했어요.</p>}{error&&<p className="error" role="alert">이름, 이메일 모양, 휴대폰 번호를 확인해 주세요.</p>}
  <form action={saveMe} className="manual-form"><label>이름<input name="name" required maxLength={60} defaultValue={me.name||''}/></label>
   <label>연락 이메일<input type="email" name="email" maxLength={254} defaultValue={me.email||''}/></label>
   <label>휴대폰 번호<input name="phone" maxLength={30} inputMode="tel" defaultValue={me.phone||''}/></label>
   <button className="primary">저장</button></form>
  <form action={logout}><button>로그아웃</button></form></main>;
}
