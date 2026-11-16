import { NextRequest, NextResponse } from 'next/server';
import { supabase } from '../../../lib/supabase';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const origin = process.env.PASSO_SITE_URL;
  if (!origin) return new NextResponse('로그인 연결을 준비하고 있습니다.', { status: 503 });
  const destination = (path: string) => {
    const response = NextResponse.redirect(new URL(path, origin));
    response.headers.set('Cache-Control', 'private, no-store');
    response.headers.set('Referrer-Policy', 'no-referrer');
    return response;
  };
  const code = request.nextUrl.searchParams.get('code');
  if (!code || code.length > 4096 || request.nextUrl.searchParams.has('error')) {
    return destination('/login?error=oauth');
  }
  const next = request.nextUrl.searchParams.get('next') || '/';
  const back = /^\/invite\/[0-9a-f]{64}$/.test(next) || next === '/reset' ? next : '/';
  const sb = await supabase();
  const { error } = await sb.auth.exchangeCodeForSession(code);
  if (error) return destination('/login?error=oauth');
  if (back === '/reset') return destination('/reset');  // 비밀번호 찾기 메일: 새 비밀번호를 정한 뒤에 잇는다
  // 예전 Google 계정은 공급자 번호로 먼저 잇고, 그 밖의 사람(새 가입 · 이메일 · 카카오)은 passo 사람을 만들거나 같은 이메일의 예전 계정에 잇는다.
  await sb.rpc('passo_link_google_identity');
  const { data: linked, error: linkError } = await sb.rpc('passo_register_self', {});
  if (linkError || linked !== true) {
    await sb.auth.signOut({ scope: 'local' });
    return destination('/login?error=unlinked');
  }
  return destination(back);
}
