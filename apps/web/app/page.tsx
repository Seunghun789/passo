import { api } from '../lib/api';
import { supabase, configured } from '../lib/supabase';
import { redirect } from 'next/navigation';
import Workspace from './workspace';
import Landing from './landing';
export const dynamic='force-dynamic';
export const maxDuration=300;
export default async function Home({searchParams}:{searchParams:Promise<{workspace?:string,view?:string,period?:string}>}) {
 if(!configured()) return <Landing/>;
 const sb=await supabase();const {data}=await sb.auth.getClaims();const user=data?.claims;
 if(!user) return <Landing/>;  // 로그인하지 않은 첫 방문은 랜딩. 로그인해 있으면 랜딩 없이 앱으로
 const params=await searchParams;
 const workspaces=await api('/v1/workspaces');
 // 가입하고 처음 들어오면 워크스페이스를 하나 만들고 빈 올리기를 연다
 if(!workspaces.length){const {id}=await api('/v1/workspaces',{method:'POST',body:JSON.stringify({title:'내 워크스페이스'})});redirect(`/?workspace=${id}&view=upload`);}
 // The API orders accessible spaces by this account's last actual visit.
 if(!params.workspace&&workspaces.length) redirect(`/?workspace=${workspaces[0].id}&view=home`);
 const selected=workspaces.find((w:{id:number})=>String(w.id)===params.workspace)??(!params.workspace?workspaces[0]:undefined);
 const period=['오늘','이번 주','이번 달','올해'].includes(params.period||'')?params.period!:'이번 주';
 const [me,{admin},overview]=await Promise.all([api('/v1/me'),api('/v1/admin/me'),  // 서로 기다릴 필요 없는 것은 함께 부른다
  selected?api(`/v1/workspaces/${selected.id}/overview?period=${encodeURIComponent(period)}`):Promise.resolve(null)]);
 return <Workspace key={selected?.id??'none'} workspaces={workspaces} selected={selected} initial={overview}
  view={params.view||'home'} name={me?.name||user?.user_metadata?.full_name||user?.user_metadata?.name||'내 계정'} email={user?.email||''} admin={!!admin}/>;
}
