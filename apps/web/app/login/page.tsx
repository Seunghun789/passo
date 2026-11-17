import { login, googleLogin, kakaoLogin, signup, requestReset } from '../actions';
import { configured } from '../../lib/supabase';
import { STEPS } from '../steps';
import { LegalLinks } from '../legal';
export const dynamic='force-dynamic';
const ERRORS:Record<string,string>={
 unlinked:'계정을 잇지 못했어요. 이메일 확인을 마쳤는지 보고 다시 로그인해 주세요.',
 oauth:'로그인을 완료하지 못했습니다. 다시 시도해 주세요.',
 session:'세션이 종료되었거나 계정 연결이 필요합니다. 다시 로그인해 주세요.',
 signup:'가입하지 못했어요. 이름, 이메일, 8자 이상 비밀번호를 확인해 주세요. 이미 가입한 이메일이면 로그인해 주세요.',
 agree:'이용약관과 개인정보처리방침에 동의하고 만 14세 이상인지 확인해 주세요.',
 config:'로그인 연결을 준비하고 있습니다.',
};
const NOTICES:Record<string,string>={
 'check-email':'확인 메일을 보냈어요. 메일의 링크를 누르면 가입이 끝나고 바로 들어와요.',
 'reset-sent':'가입한 이메일이면 비밀번호를 다시 정하는 링크를 보냈어요.',
};
export default async function Login({searchParams}:{searchParams:Promise<{error?:string,mode?:string,notice?:string,next?:string}>}) {
 const {error,mode,notice,next}=await searchParams;
 const back=/^\/invite\/[0-9a-f]{64}$/.test(next||'')?next!:'';
 const tab=mode==='signup'?'signup':mode==='reset'?'reset':'login';
 const q=(m:string)=>`/login?mode=${m}${back?`&next=${encodeURIComponent(back)}`:''}`;
 const ready=configured(),site=!!process.env.PASSO_SITE_URL;  // 메일 · 외부 로그인은 돌아올 주소(PASSO_SITE_URL)가 있어야 한다
 const email=<form action={login}><input type="hidden" name="next" value={back}/>
   <label>이메일<input type="email" name="email" autoComplete="username" required maxLength={254}/></label>
   <label>비밀번호<input type="password" name="password" autoComplete="current-password" required maxLength={1024}/></label>
   <button type="submit" className="primary">로그인</button></form>;
 return <div className="login-split"><a className="brand login-brand" href="/">passo</a>
 <main className="login">
 <h1>{tab==='signup'?'처음 오셨군요.':tab==='reset'?'비밀번호를 다시 정해요.':'손으로 적은 기록을 찍으면'}{tab==='login'&&<><br/>표 · 챙길 일 · 답이 돼요</>}</h1>
 <p>{tab==='signup'?'가입하면 바로 종이를 올릴 수 있어요.':tab==='reset'?'가입한 이메일로 링크를 보내 드려요.':'점검표, 재고 장부, 메모를 사진으로 올리세요. AI가 칸을 찾아 표로 정리하고, 틀리면 위험한 값만 물어요.'}</p>
 {notice&&NOTICES[notice]&&<p className="success" role="status">{NOTICES[notice]}</p>}
 {error&&<p className="error" role="alert">{ERRORS[error]||'로그인 정보를 확인해 주세요.'}</p>}
 {!ready?<aside>로그인 연결을 준비하고 있습니다.</aside>:<div className="auth-box">
  {tab==='login'&&(site?<details className="email-login" open={!!error}><summary className="button">이메일로 로그인</summary>{email}</details>:email)}
  {site&&tab!=='reset'&&<p className="consent-note">Google · 카카오로 처음 가입하면 <a href="/terms" target="_blank">이용약관</a>과 <a href="/privacy" target="_blank">개인정보처리방침</a>에 동의하고 만 14세 이상인 것으로 봐요. passo는 AI가 종이를 읽고 정리하는 서비스예요.</p>}
  {site&&tab!=='reset'&&<div className="oauth">
   <form action={googleLogin}><input type="hidden" name="next" value={back}/><button type="submit">Google로 계속하기</button></form>
   {process.env.PASSO_KAKAO==='on'?<form action={kakaoLogin}><input type="hidden" name="next" value={back}/><button type="submit" className="kakao">카카오로 계속하기</button></form>
    :<details className="kakao-soon"><summary className="button kakao">카카오로 계속하기</summary><p className="info">카카오 로그인은 준비 중이에요. 지금은 이메일이나 Google로 시작해요.</p></details>}
  </div>}
  {tab==='login'&&site&&<p className="login-links"><a href={q('signup')}>처음이에요 · 회원가입</a><br/><a href={q('reset')}>비밀번호를 잊었어요</a></p>}
  {site&&tab==='signup'&&<form action={signup}><input type="hidden" name="next" value={back}/>
   <label>이름<input name="name" autoComplete="name" required maxLength={60}/></label>
   <label>이메일<input type="email" name="email" autoComplete="email" required maxLength={254}/></label>
   <label>비밀번호 (8자 이상)<input type="password" name="password" autoComplete="new-password" required minLength={8} maxLength={1024}/></label>
   <label className="agree"><input type="checkbox" name="agree" required/><span>[필수] <a href="/terms" target="_blank">이용약관</a>과 <a href="/privacy" target="_blank">개인정보처리방침</a>(AI 처리 · 국외 이전 포함)에 동의하고, 만 14세 이상이에요.</span></label>
   <button type="submit" className="primary">이메일로 회원가입</button>
   <p className="login-links"><a href={q('login')}>이미 계정이 있어요 · 로그인</a></p></form>}
  {site&&tab==='reset'&&<form action={requestReset}>
   <label>가입한 이메일<input type="email" name="email" autoComplete="email" required maxLength={254}/></label>
   <button type="submit" className="primary">링크 보내기</button>
   <p className="login-links"><a href={q('login')}>로그인</a></p></form>}
 </div>}<LegalLinks/></main>
 <aside className="login-steps" aria-label="쓰는 순서">{STEPS.map(([h,p],i)=><div key={h} className={`step-card${i===0?' on':''}`}><b>{h}</b><p>{p}</p></div>)}</aside>
 </div>;
}
