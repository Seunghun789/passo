// 017: 직접 고친 것은 카드로 올라가고 [적용] 때만 반영된다. 확인하는 사람만, 이 워크스페이스만.
export async function editCases({db,as,denied,check}) {
 const one=async(sql,args=[])=>(await db.query(sql,args)).rows[0];
 const card=(n,kind,payload,tid=1)=>as(n,'select public.passo_user_card($1,$2,$3) as id',[tid,kind,payload]);
 const apply=(n,id,ok=true,tid=1)=>as(n,'select public.passo_user_card_answer($1,$2,$3) as r',[tid,id,ok]);
 // 015 의 설비 분류 · P-03 · P-07 · P-09 를 쓴다
 const attr=(await card(1,'대상 속성',{class:'설비',attr:'설치일',dtype:'date'}))[0].id;
 check('edit becomes a pending user card',(await one('select status,evidence from proposals where id=$1',[attr])).status==='대기');
 check('pending card changes nothing yet',!(await one("select 1 from property_defs where tenant_id=1 and type_name='설비' and name='설치일'")));
 await apply(1,attr);
 check('[적용] adds the attribute',(await one("select dtype from property_defs where tenant_id=1 and type_name='설비' and name='설치일'")).dtype==='date');
 const p03=(await one("select id from entities where tenant_id=1 and name='P-03'")).id;
 const val=(await card(1,'속성 값',{entity_id:p03,entity:'P-03',class:'설비',attr:'설치일',old:null,new:'2026-01-02'}))[0].id;
 await apply(1,val);
 check('attribute value applied',(await one('select attrs from entities where id=$1',[p03])).attrs['설치일']==='2026-01-02');
 const bad=(await card(1,'속성 값',{entity_id:p03,attr:'없는 정보',new:'x'}))[0].id;
 await denied('value for an unknown attribute is refused',()=>apply(1,bad));
 const al=(await card(1,'같은 대상',{class:'설비',value:'프레스 3',same_as:'P-03'}))[0].id;
 await apply(1,al);
 check('alias applied',(await one("select count(*)::int n from entity_aliases where tenant_id=1 and alias='프레스 3' and entity_id=$1",[p03])).n===1);
 const grp=(await card(1,'상위 분류',{class:'프레스',parent:'설비',members:['P-03','P-07']}))[0].id;
 await apply(1,grp);
 check('sub class groups members',(await one("select parent_name from object_types where tenant_id=1 and name='프레스'")).parent_name==='설비'
  &&(await one("select count(*)::int n from entities where tenant_id=1 and class_name='프레스'")).n===2);
 const loop=(await card(1,'상위 분류',{class:'설비',parent:'프레스',members:[]}))[0].id;
 await denied('class loop refused',()=>apply(1,loop));
 const up=(await card(1,'상위 분류',{class:'설비',parent:'자산',members:[]}))[0].id;
 await apply(1,up);
 check('parent class set',(await one("select parent_name from object_types where tenant_id=1 and name='설비'")).parent_name==='자산');
 const ty=(await card(1,'칸 설정',{type:'설비 점검',op:'단위·설명',prop:'진동',unit:'mm/s',description:'측정한 진동'}))[0].id;
 await apply(1,ty);
 check('unit and description applied',(await one("select unit,description from property_defs where tenant_id=1 and type_name='설비 점검' and name='진동'")).unit==='mm/s');
 const al2=(await card(1,'칸 설정',{type:'설비 점검',op:'다른 이름',prop:'진동',alias:'진동값'}))[0].id;
 await apply(1,al2);
 check('other name maps to the column',(await one("select prop_name from alias_dict where tenant_id=1 and type_name='설비 점검' and alias='진동값'")).prop_name==='진동');
 const add=(await card(1,'칸 설정',{type:'설비 점검',op:'칸 더하기',name:'온도',dtype:'number',unit:'℃'}))[0].id;
 await apply(1,add);
 check('new column added',(await one("select dtype,unit from property_defs where tenant_id=1 and type_name='설비 점검' and name='온도'")).unit==='℃');
 await db.exec("insert into object_types(tenant_id,name,kind) values(1,'정비사','대상') on conflict do nothing");
 await db.exec("insert into entities(tenant_id,class_name,name) values(1,'정비사','김정비') on conflict do nothing");
 await db.exec("insert into entity_aliases(tenant_id,entity_id,alias) select 1,id,name from entities where tenant_id=1 and name='김정비' on conflict do nothing");
 const link=(await one("insert into link_types(tenant_id,from_ref,to_ref,kind,name) values(1,'설비','정비사','연결','담당') returning id")).id;
 const la=(await card(1,'관계 속성',{link_id:link,attr:'점검 주기',dtype:'number',values:{'P-03|김정비':7,'없는|김정비':1}}))[0].id;
 const res=(await apply(1,la))[0].r;
 check('link attribute and pair values applied',res.count===1&&(await one('select attr_defs from link_types where id=$1',[link])).attr_defs[0].name==='점검 주기'
  &&(await one('select attrs from entity_links where link_id=$1',[link])).attrs['점검 주기']===7);
 const no=(await card(1,'대상 속성',{class:'설비',attr:'버릴 정보',dtype:'text'}))[0].id;
 await apply(1,no,false);
 check('[아니요] leaves things unchanged',(await one('select status from proposals where id=$1',[no])).status==='거절'
  &&!(await one("select 1 from property_defs where tenant_id=1 and type_name='설비' and name='버릴 정보'")));
 await denied('answered card cannot be applied again',()=>apply(1,no));
 await denied('viewer cannot raise edit cards',()=>card(3,'대상 속성',{class:'설비',attr:'x',dtype:'text'}));
 await denied('unknown card kind refused',()=>card(1,'종류',{}));
 const mine=(await card(1,'대상 속성',{class:'설비',attr:'y',dtype:'text'}))[0].id;
 await denied('viewer cannot apply',()=>apply(3,mine));
 await denied('another workspace cannot apply',()=>apply(2,mine,true,2));
 const ai=(await one("select id from proposals where tenant_id=1 and kind='같은 대상' and status='승인' and evidence->>'auto'='true' limit 1"));
 await db.query("update proposals set status='대기' where id=$1",[ai.id]);
 await denied('non-user cards are not applied through edits',()=>apply(1,ai.id));
 await db.query("update proposals set status='승인' where id=$1",[ai.id]);
}
