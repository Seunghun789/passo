'use server';
import { redirect } from 'next/navigation';
import { revalidatePath } from 'next/cache';
import { supabase, configured } from '../lib/supabase';
import { api, apiResponse } from '../lib/api';

// 로그인 뒤 돌아갈 곳: 초대 링크만 허락한다(다른 사이트로 보내지 않는다).
function safeNext(v: FormDataEntryValue | string | null) {
  const next = String(v || '');
  return /^\/invite\/[0-9a-f]{64}$/.test(next) ? next : '/';
}
function callbackUrl(next: string) {
  const u = new URL('/auth/callback', process.env.PASSO_SITE_URL);
  if (next !== '/') u.searchParams.set('next', next);
  return u.href;
}
async function oauth(provider: 'google' | 'kakao', form?: FormData) {
  if (!configured() || !process.env.PASSO_SITE_URL) redirect('/login?error=config');
  const sb = await supabase();
  const { data, error } = await sb.auth.signInWithOAuth({
    provider,
    options: { redirectTo: callbackUrl(safeNext(form?.get('next') ?? null)),
      ...(provider === 'google' ? { queryParams: { prompt: 'select_account' } } : {}) },
  });
  if (error || !data.url) redirect('/login?error=oauth');
  redirect(data.url);
}
export async function googleLogin(form?: FormData) { await oauth('google', form); }
export async function kakaoLogin(form?: FormData) { await oauth('kakao', form); }

export async function signup(form: FormData) {
  if (!configured() || !process.env.PASSO_SITE_URL) redirect('/login?error=config');
  const name = String(form.get('name') || '').trim().slice(0, 60);
  const email = String(form.get('email') || '').trim();
  const password = String(form.get('password') || '');
  const next = safeNext(form.get('next'));
  if (!name || email.length > 254 || password.length < 8 || password.length > 1024) redirect('/login?mode=signup&error=signup');
  const sb = await supabase();
  const { data, error } = await sb.auth.signUp({ email, password,
    options: { emailRedirectTo: callbackUrl(next), data: { full_name: name } } });
  if (error) redirect('/login?mode=signup&error=signup');
  if (!data.session) redirect('/login?notice=check-email');  // 메일의 확인 링크를 누르면 /auth/callback 으로 돌아온다
  await sb.rpc('passo_register_self', { display_name: name });
  redirect(next);
}

export async function requestReset(form: FormData) {
  if (!configured() || !process.env.PASSO_SITE_URL) redirect('/login?error=config');
  const email = String(form.get('email') || '').trim();
  if (email && email.length <= 254) {
    const sb = await supabase();
    const u = new URL('/auth/callback', process.env.PASSO_SITE_URL); u.searchParams.set('next', '/reset');
    await sb.auth.resetPasswordForEmail(email, { redirectTo: u.href });
  }
  redirect('/login?notice=reset-sent');  // 계정이 있는지 알려 주지 않는다
}

export async function resetPassword(form: FormData) {
  const password = String(form.get('password') || '');
  if (password.length < 8 || password.length > 1024) redirect('/reset?error=short');
  const sb = await supabase();
  const { error } = await sb.auth.updateUser({ password });
  if (error) redirect('/reset?error=failed');
  redirect('/');
}

export async function createWorkspace(form: FormData) {
  const title = String(form.get('title') || '').trim().slice(0, 60) || '내 워크스페이스';
  const { id } = await api('/v1/workspaces', { method: 'POST', body: JSON.stringify({ title }) });
  redirect(`/?workspace=${id}&view=upload`);
}

export async function saveMe(form: FormData) {
  const body = { name: String(form.get('name') || '').trim(), email: String(form.get('email') || '').trim(), phone: String(form.get('phone') || '').trim() };
  if (!body.name || body.name.length > 60 || body.email.length > 254 || body.phone.length > 30) redirect('/account?error=invalid');
  const r = await apiResponse('/v1/me', { method: 'POST', body: JSON.stringify(body) }, true);
  redirect(r.ok ? '/account?saved=1' : '/account?error=invalid');
}

export async function acceptInvite(form: FormData) {
  const token = String(form.get('token') || '');
  if (!/^[0-9a-f]{64}$/.test(token)) redirect('/');
  const r = await apiResponse(`/v1/invites/${token}`, { method: 'POST', body: '{}' }, true);
  if (!r.ok) redirect(`/invite/${token}?error=used`);
  const { workspace } = await r.json();
  redirect(`/?workspace=${workspace}&view=home`);
}

export async function login(form: FormData) {
  if (!configured()) redirect('/login?error=config');
  const email = String(form.get('email') || '').trim();
  const password = String(form.get('password') || '');
  if (email.length > 254 || password.length > 1024) redirect('/login?error=credentials');
  const sb = await supabase();
  const { error } = await sb.auth.signInWithPassword({email,password});
  if (error) redirect('/login?error=credentials');
  await sb.rpc('passo_register_self', {});  // 메일 확인을 마친 새 계정 · 같은 이메일의 예전 계정을 잇는다
  redirect(safeNext(form.get('next')));
}
export async function logout() {
  const sb = await supabase();
  const {error} = await sb.auth.signOut({scope:'local'});
  if (error) throw new Error('로그아웃을 완료하지 못했습니다. 다시 시도해 주세요.');
  redirect('/login');
}
export async function editCell(form: FormData) {
  const tid=String(form.get('tid')), rid=String(form.get('rid'));
  if (!/^[1-9]\d*$/.test(tid) || !/^[1-9]\d*$/.test(rid)) throw new Error('잘못된 기록 번호입니다.');
  const raw=String(form.get('value') || '');
  const label=String(form.get('label') || '');
  const expected=String(form.get('expected') || '');
  if (raw.length>10000 || label.length>200 || expected.length>65536) throw new Error('입력 크기를 줄여 주세요.');
  await api(`/v1/workspaces/${tid}/records/${rid}/cells`, {
    method:'PATCH',body:JSON.stringify({expected_data:JSON.parse(expected), changes:{[label]:raw}}),
  });
  revalidatePath('/');
}
