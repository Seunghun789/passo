import { resetPassword } from '../actions';
import { supabase, configured } from '../../lib/supabase';
import { redirect } from 'next/navigation';
export const dynamic='force-dynamic';
export default async function Reset({searchParams}:{searchParams:Promise<{error?:string}>}) {
 if(!configured()) redirect('/login');
 const sb=await supabase();const {data:{user}}=await sb.auth.getUser();
 if(!user) redirect('/login?mode=reset');
 const {error}=await searchParams;
 return <main className="login"><p className="eyebrow">비밀번호 다시 정하기</p><h1>새 비밀번호를 정해요.</h1>
  {error&&<p className="error" role="alert">{error==='short'?'비밀번호는 8자 이상으로 정해 주세요.':'저장하지 못했어요. 링크를 다시 받아 주세요.'}</p>}
  <form action={resetPassword}><label>새 비밀번호 (8자 이상)<input type="password" name="password" autoComplete="new-password" required minLength={8} maxLength={1024}/></label>
  <button type="submit" className="primary">저장</button></form></main>;
}
