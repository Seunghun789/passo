// 013: 자동화 켜기·끄기, 지표 올리기·내리기는 확인하는 사람 이상만, 이 워크스페이스 줄만 바꾼다.
export async function rulesCases({db,as,denied,check}) {
 const spec={title:'수량 부족',type:'재고 점검',scope:'latest',conditions:[{prop:'수량',op:'<',value:'5'}]};
 const add=(n,fn,tid=1,s=spec)=>as(n,`select public.${fn}($1,$2) as id`,[tid,s]);
 const id=(await add(1,'passo_automation_add'))[0].id;
 check('owner turns on automation',Number(id)>0);
 check('same title is not added twice',(await add(1,'passo_automation_add'))[0].id===id&&(await db.query("select count(*)::int n from automations where spec->>'title'='수량 부족'")).rows[0].n===1);
 await denied('viewer cannot turn on automation',()=>add(3,'passo_automation_add'));
 await denied('uploader cannot turn on automation',()=>add(5,'passo_automation_add'));
 await denied('foreign workspace automation denied',()=>add(2,'passo_automation_add'));
 await denied('rule without title rejected',()=>add(1,'passo_automation_add',1,{type:'재고 점검'}));
 await denied('oversized rule rejected',()=>add(1,'passo_automation_add',1,{...spec,title:'x',pad:'가'.repeat(30000)}));
 const status=(n,s,tid=1,aid=id)=>as(n,'select public.passo_automation_status($1,$2,$3)',[tid,aid,s]);
 await status(1,'꺼짐');
 check('automation turned off',(await db.query('select status from automations where id=$1',[id])).rows[0].status==='꺼짐');
 await add(1,'passo_automation_add');
 check('turning on the same rule again re-enables it',(await db.query('select status from automations where id=$1',[id])).rows[0].status==='켜짐');
 await denied('viewer cannot turn off automation',()=>status(3,'꺼짐'));
 await denied('unknown automation status rejected',()=>status(1,'삭제'));
 await denied('automation of another workspace cannot be changed',()=>status(1,'꺼짐',1,999999));
 await denied('B cannot change A automation through B workspace',()=>status(2,'꺼짐',2));
 check('members can read automations',(await as(3,'select id from public.automations')).length===1);
 check('other workspace sees no automations',(await as(2,'select id from public.automations')).length===0);
 const w=(await add(1,'passo_widget_add',1,{...spec,title:'수량 부족 건수',kind:'count_where'}))[0].id;
 await as(1,'select public.passo_widget_status($1,$2,$3)',[1,w,'내림']);
 check('widget taken down',(await db.query('select status from widgets where id=$1',[w])).rows[0].status==='내림');
 await denied('viewer cannot put up widget',()=>add(3,'passo_widget_add',1,{...spec,title:'다른 지표'}));
 await denied('unknown widget status rejected',()=>as(1,'select public.passo_widget_status($1,$2,$3)',[1,w,'숨김']));
 await denied('direct automation insert stays denied',()=>as(1,"insert into public.automations(tenant_id,spec) values(1,'{}')"));
 let anon=false; try{await as(1,'select public.passo_automation_add(1,$1)',[spec],'anon');}catch{anon=true;}
 check('anonymous cannot turn on automation',anon);
}
