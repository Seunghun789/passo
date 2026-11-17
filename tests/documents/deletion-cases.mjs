// 022: [owner 넘기기]는 주인만, 구성원에게. [계정 지우기]는 함께 쓰는 워크스페이스의 주인이면 막고(먼저 넘기기),
// 혼자 쓰는 워크스페이스는 기록 · AI 기록과 함께 지우고, 다른 워크스페이스에 남긴 것은 남기되 누가 했는지만 지운다. 1년 지난 기록은 지운다.
export async function deletionCases({db,as,denied,check,uid}) {
 const one=async(sql,args=[])=>(await db.query(sql,args)).rows[0];
 const sid=n=>uid(n+100);
 const person=async(n,email)=>{
  await db.query('insert into auth.users(id,email,email_confirmed_at) values($1,$2,now())',[uid(n),email]);
  await db.query('insert into auth.sessions(id,user_id) values($1,$2)',[sid(n),uid(n)]);
  await as(n,'select public.passo_register_self($1)',[email],'authenticated',{app_metadata:{provider:'email'}});
  return (await one('select legacy_user_id id from auth_identity_links where auth_user_id=$1',[uid(n)])).id;
 };
 const A=await person(60,'a60@example.com'), B=await person(61,'b61@example.com'), C=await person(62,'c62@example.com');
 const create=(n,title)=>as(n,'select public.passo_workspace_create($1) as id',[title]).then(r=>Number(r[0].id));
 const alone=await create(60,'혼자'), shared=await create(60,'함께'), others=await create(62,'다른 사람');
 await db.query("insert into memberships(tenant_id,user_id,role) values($1,$2,'올리는 사람'),($3,$4,'보는 사람')",[shared,B,others,A]);
 const path=`${alone}/${uid(601)}/a.png`;
 await db.query("insert into source_inputs(tenant_id,channel,storage_path,created_by) values($1,'사진',$2,$3),($4,'사진',null,$3)",[alone,path,A,others]);
 await db.query("insert into records(tenant_id,type_name,occurred_at,data) values($1,'점검','2026-11-17','{}')",[alone]);
 await db.query("insert into ai_logs(model,prompt,answer,input_tokens,output_tokens,cost_usd,tenant_id) values('m','p','a',1,1,0,$1)",[alone]);
 // 워크스페이스를 지우면 AI 기록도 함께 지워진다
 const gone=await create(62,'지울 것');
 await db.query("insert into ai_logs(model,prompt,answer,input_tokens,output_tokens,cost_usd,tenant_id) values('m','gone','a',1,1,0,$1)",[gone]);
 await db.query('delete from tenants where id=$1',[gone]);
 check('deleting a workspace removes its AI logs',(await one("select count(*)::int n from ai_logs where prompt='gone'")).n===0);
 const del=(n,dry)=>as(n,'select public.passo_delete_me($1) as r',[dry]).then(r=>r[0].r);
 const transfer=(n,tid,member)=>as(n,'select public.passo_owner_transfer($1,$2)',[tid,member]);

 // [owner 넘기기]
 await denied('non-owner cannot hand over ownership',()=>transfer(61,shared,B));
 await denied('ownership goes only to a member',()=>transfer(60,shared,C));
 await denied('owner cannot hand over to themself',()=>transfer(60,shared,A));

 // 함께 쓰는 워크스페이스의 주인은 먼저 넘겨야 지울 수 있다
 const plan=await del(60,true);
 check('deletion preview lists shared workspace as blocking',plan.blocked.map(x=>Number(x.id)).join()===String(shared));
 check('deletion preview lists solo workspace to be deleted',plan.workspaces.map(x=>Number(x.id)).join()===String(alone));
 const refused=await del(60,false);
 check('deletion refused while owning a shared workspace',refused.deleted===false&&!!(await one('select id from users where id=$1',[A])));

 await transfer(60,shared,B);
 check('new owner holds the workspace',(await as(61,"select public.passo_access($1,'review') ok",[shared]))[0].ok===true
  &&(await one("select role from memberships where tenant_id=$1 and user_id=$2",[shared,B])).role==='주인');
 check('previous owner stays as reviewer',(await one("select role from memberships where tenant_id=$1 and user_id=$2",[shared,A])).role==='확인하는 사람');
 await denied('previous owner can no longer hand over',()=>transfer(60,shared,B));
 check('workspace moved to the new owner organization',(await one('select count(*)::int n from org_members m join tenants t on t.org_id=m.org_id where t.id=$1 and m.user_id=$2 and m.role=$3',[shared,B,'주인'])).n===1);

 // 지우기
 const done=await del(60,false);
 check('account deletion succeeds after hand-over',done.deleted===true);
 check('deletion returns original file paths of deleted workspaces',JSON.stringify(done.paths)===JSON.stringify([path]));
 check('solo workspace and its records are gone',!(await one('select id from tenants where id=$1',[alone]))&&(await one('select count(*)::int n from records where tenant_id=$1',[alone])).n===0);
 check('AI log of the deleted workspace is gone',(await one('select count(*)::int n from ai_logs where tenant_id=$1 or (tenant_id is null and prompt=$2)',[alone,'p'])).n===0);
 check('shared workspace stays with its new owner',!!(await one('select id from tenants where id=$1',[shared])));
 check('paper left in another workspace stays without its author',(await one('select created_by from source_inputs where tenant_id=$1',[others])).created_by===null);
 check('person and login account are gone',!(await one('select id from users where id=$1',[A]))&&!(await one('select id from auth.users where id=$1',[uid(60)])));
 check('memberships of the deleted person are gone',(await one('select count(*)::int n from memberships where user_id=$1',[A])).n===0);
 await denied('deleted account cannot call again',()=>del(60,true));

 // 1년 지난 AI 기록 · 작업 기록
 await db.query("insert into ai_logs(model,prompt,answer,input_tokens,output_tokens,cost_usd,tenant_id,created_at) values('m','old','a',1,1,0,$1,now()-interval '13 months'),('m','new','a',1,1,0,$1,now())",[shared]);
 await db.query("insert into passo_audit(tenant_id,operation,before_state,after_state,reversible,created_at) values($1,'old','{}','{}',false,now()-interval '13 months'),($1,'new','{}','{}',false,now())",[shared]);
 await db.exec('select passo_private.retention()');
 check('retention removes AI logs older than a year',(await one("select string_agg(prompt,',' order by prompt) s from ai_logs where tenant_id=$1",[shared])).s==='new');
 check('retention removes work logs older than a year',(await one("select string_agg(operation,',' order by operation) s from passo_audit where tenant_id=$1",[shared])).s==='new');
}
