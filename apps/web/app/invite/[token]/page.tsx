import { acceptInvite } from '../../actions';
import { apiResponse } from '../../../lib/api';
import { supabase, configured } from '../../../lib/supabase';
import { redirect } from 'next/navigation';
export const dynamic='force-dynamic';
export default async function Invite({params,searchParams}:{params:Promise<{token:string}>,searchParams:Promise<{error?:string}>}) {
 const {token}=await params;const {error}=await searchParams;
 if(!/^[0-9a-f]{64}$/.test(token)||!configured()) redirect('/');
 const sb=await supabase();const {data:{user}}=await sb.auth.getUser();
 if(!user) redirect(`/login?next=${encodeURIComponent('/invite/'+token)}`);
 const r=await apiResponse(`/v1/invites/${token}`,{},true);
 const invite=r.ok?await r.json():null;
 return <main className="login"><p className="eyebrow">초대</p>
  {!invite?<><h1>초대 링크를 찾지 못했어요.</h1><p>링크를 보낸 사람에게 새 링크를 받아 주세요.</p><a className="button" href="/">홈으로</a></>:<>
  <h1>&apos;{invite.title}&apos;에 초대받았어요.</h1><p>{invite.role}(으)로 참여해요.</p>
  {error&&<p className="error" role="alert">이미 쓴 링크이거나 기간이 지났어요.</p>}
  {invite.valid?<form action={acceptInvite}><input type="hidden" name="token" value={token}/><button type="submit" className="primary">참여하기</button></form>
   :<p className="info">이미 쓴 링크이거나 7일이 지났어요. 새 링크를 받아 주세요.</p>}</>}</main>;
}
