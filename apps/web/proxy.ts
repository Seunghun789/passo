import { createServerClient } from '@supabase/ssr';
import { NextResponse, type NextRequest } from 'next/server';
export async function proxy(request: NextRequest) {
  let response = NextResponse.next({request});
  if (!process.env.SUPABASE_URL || !process.env.SUPABASE_PUBLISHABLE_KEY) return response;
  const sb = createServerClient(process.env.SUPABASE_URL, process.env.SUPABASE_PUBLISHABLE_KEY, {
    cookieOptions:{httpOnly:true, sameSite:'lax', secure:process.env.NODE_ENV==='production', path:'/'},
    cookies:{getAll:()=>request.cookies.getAll(), setAll(values){
      values.forEach(({name,value})=>request.cookies.set(name,value));
      response=NextResponse.next({request});
      values.forEach(({name,value,options})=>response.cookies.set(name,value,options));
    }},
  });
  // 세션을 새로 고치고(만료되면) 확인한다. API 서버가 받은 토큰을 다시 확인하므로, 뒤의 화면 · API 는 쿠키의 세션만 꺼내 쓴다
  await sb.auth.getClaims();
  response.headers.set('Cache-Control','private, no-store');
  return response;
}
export const config = {matcher:['/((?!_next/static|_next/image|favicon.ico|manifest.webmanifest|icon|apple-icon|fonts/).*)']};
