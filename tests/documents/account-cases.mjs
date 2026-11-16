// 019: 가입은 메일 확인 뒤에만 잇고, 같은 이메일의 예전 계정에 잇는다. 초대 · 구성원 · 워크스페이스 정보는 주인만 바꾼다.
export async function accountCases({db,as,denied,check,uid}) {
 const one=async(sql,args=[])=>(await db.query(sql,args)).rows[0];
 const sid=n=>uid(n+100);
 const newAuth=async(n,email,confirmed=true,meta={})=>{
  await db.query('insert into auth.users(id,email,email_confirmed_at,raw_user_meta_data) values($1,$2,$3,$4)',[uid(n),email,confirmed?new Date().toISOString():null,meta]);
  await db.query('insert into auth.sessions(id,user_id) values($1,$2)',[sid(n),uid(n)]);
 };
 const reg=(n,provider='email',name=null)=>as(n,'select public.passo_register_self($1) as ok',[name],'authenticated',{app_metadata:{provider}}).then(r=>r[0].ok);
 // 메일 확인 전에는 잇지 않는다
 await newAuth(40,'new@example.com',false);
 check('unconfirmed email is not linked',await reg(40)===false);
 await db.query('update auth.users set email_confirmed_at=now() where id=$1',[uid(40)]);
 check('confirmed email signup creates a person',await reg(40,'email','새 사람')===true&&(await one("select name,provider from users where sub='new@example.com'")).name==='새 사람');
 check('registering again is harmless',await reg(40)===true);
 // 예전 이메일 계정(같은 이메일, 대소문자 무시)에 잇는다
 await db.query("insert into users(provider,sub,name,password_hash) values('email','Old@Example.com','예전 사람','pbkdf2$x')");
 await newAuth(41,'old@example.com');
 await reg(41);
 check('legacy email account is reused after confirmation',(await one("select u.name from auth_identity_links l join users u on u.id=l.legacy_user_id where l.auth_user_id=$1",[uid(41)])).name==='예전 사람');
 // 카카오는 공급자 번호로
 await newAuth(42,'k@example.com');
 await db.query("insert into auth.identities(user_id,provider,provider_id) values($1,'kakao','kakao-123')",[uid(42)]);
 check('kakao signup links by provider id',await reg(42,'kakao')===true&&(await one("select sub from users where provider='kakao'")).sub==='kakao-123');
 await newAuth(43,'x@example.com');
 check('unknown provider is refused',await reg(43,'github')===false);
 // 워크스페이스 만들기: 조직 주인이 되고 그 조직에 더한다
 const t1=(await as(40,"select public.passo_workspace_create('첫 공간') as id"))[0].id;
 const t2=(await as(40,"select public.passo_workspace_create('둘째 공간') as id"))[0].id;
 check('new workspaces share the owner organization',(await one('select count(distinct org_id)::int n from tenants where id in ($1,$2)',[t1,t2])).n===1);
 check('creator is owner',(await as(40,"select public.passo_access($1,'review') as ok",[t1]))[0].ok===true);
 await denied('unlinked person cannot create a workspace',()=>as(43,"select public.passo_workspace_create('x')"));
 // 초대
 const tok=(await as(40,"select public.passo_invite_create($1,'올리는 사람') as t",[t1]))[0].t;
 check('invite token is long and random',tok.length===64);
 await denied('non-owner cannot invite',()=>as(41,"select public.passo_invite_create($1,'보는 사람')",[t1]));
 await denied('owner role cannot be invited',()=>as(40,"select public.passo_invite_create($1,'주인')",[t1]));
 check('invite preview shows workspace and role',(await as(41,'select public.passo_invite_preview($1) as p',[tok]))[0].p.role==='올리는 사람');
 check('wrong token shows nothing',(await as(41,'select public.passo_invite_preview($1) as p',['x'.repeat(64)]))[0].p===null);
 check('invite accept joins with the role',(await as(41,'select public.passo_invite_accept($1) as t',[tok]))[0].t===t1
  &&(await as(41,"select public.passo_access($1,'upload') as ok",[t1]))[0].ok===true&&(await as(41,"select public.passo_access($1,'review') as ok",[t1]))[0].ok===false);
 await denied('used invite cannot be used again',()=>as(42,'select public.passo_invite_accept($1)',[tok]));
 const old=(await as(40,"select public.passo_invite_create($1,'보는 사람') as t",[t1]))[0].t;
 await db.query("update invites set expires_at=now()-interval '1 minute' where token=$1",[old]);
 await denied('expired invite refused',()=>as(42,'select public.passo_invite_accept($1)',[old]));
 // 구성원
 const members=await as(41,'select * from public.passo_members($1)',[t1]);
 check('members list roles, owner email hidden from a member',members.length===2&&members.find(m=>m.role==='주인').email===null&&members.find(m=>m.me).role==='올리는 사람');
 check('owner sees emails',(await as(40,'select * from public.passo_members($1)',[t1])).find(m=>m.me).email==='new@example.com');
 const uid41=(await one('select legacy_user_id id from auth_identity_links where auth_user_id=$1',[uid(41)])).id;
 await denied('non-owner cannot change roles',()=>as(41,"select public.passo_member_role($1,$2,'확인하는 사람')",[t1,uid41]));
 await as(40,"select public.passo_member_role($1,$2,'확인하는 사람')",[t1,uid41]);
 check('owner changes a member role',(await as(41,"select public.passo_access($1,'review') as ok",[t1]))[0].ok===true);
 const me40=(await one('select legacy_user_id id from auth_identity_links where auth_user_id=$1',[uid(40)])).id;
 await denied('owner role cannot be changed',()=>as(40,"select public.passo_member_role($1,$2,'보는 사람')",[t1,me40]));
 // 정보 · 내 계정
 await as(40,"select public.passo_workspace_update($1,'바꾼 이름','재고를 적어요','우리 가게','유통','생수',null)",[t1]);
 const info=(await as(41,'select public.passo_workspace_info($1) as i',[t1]))[0].i;
 check('workspace info saved',info.title==='바꾼 이름'&&info.about==='재고를 적어요'&&info.industry==='유통'&&info.role==='확인하는 사람'&&info.org_owner===false);
 await denied('non-owner cannot change workspace info',()=>as(41,"select public.passo_workspace_update($1,'x','','','','',null)",[t1]));
 await as(41,"select public.passo_me_update('예전 사람2','old2@example.com','010-1234-5678')");
 check('account saved',(await as(41,'select * from public.passo_me()'))[0].phone==='010-1234-5678');
 await denied('bad email refused',()=>as(41,"select public.passo_me_update('a','not-an-email','')"));
 await denied('member cannot remove others',()=>as(41,'select public.passo_member_remove($1,$2)',[t1,me40]));
 await denied('owner cannot be removed',()=>as(40,'select public.passo_member_remove($1,$2)',[t1,me40]));
 await as(40,'select public.passo_member_remove($1,$2)',[t1,uid41]);
 check('[내보내기] removes the workspace from that person',(await as(41,'select id from public.passo_workspaces()')).every(w=>w.id!==t1));
 await denied('foreign workspace info hidden',()=>as(2,'select public.passo_workspace_info($1)',[t1]));
}
