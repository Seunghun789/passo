// 018: 직접 고친 것의 [되돌리기]는 고치기 전으로 정확히, 그 뒤에 바뀌었으면 되돌리지 않는다.
export async function undoCases({db,as,denied,check}) {
 const one=async(sql,args=[])=>(await db.query(sql,args)).rows[0];
 const card=(kind,payload)=>as(1,'select public.passo_user_card(1,$1,$2) as id',[kind,payload]).then(r=>r[0].id);
 const apply=id=>as(1,'select public.passo_user_card_answer(1,$1,true)',[id]);
 const undo=(id,n=1)=>as(n,'select public.passo_user_card_undo(1,$1)',[id]);
 const p03=(await one("select id from entities where tenant_id=1 and name='P-03'")).id;
 const v=await card('속성 값',{entity_id:p03,attr:'설치일',old:'2026-01-02',new:'2026-03-04'});await apply(v);
 await denied('viewer cannot undo',()=>undo(v,3));
 await undo(v);
 check('attribute value goes back',(await one('select attrs from entities where id=$1',[p03])).attrs['설치일']==='2026-01-02');
 await denied('undone card cannot be undone again',()=>undo(v));
 const v2=await card('속성 값',{entity_id:p03,attr:'설치일',old:'2026-01-02',new:'2026-05-05'});await apply(v2);
 await db.query("update entities set attrs=attrs||'{\"설치일\":\"2026-06-06\"}' where id=$1",[p03]);
 await denied('later change prevents undo',()=>undo(v2));
 const al=await card('같은 대상',{class:'설비',value:'세 번째 프레스',same_as:'P-03'});await apply(al);
 await undo(al);
 check('alias removed on undo',!(await one("select 1 from entity_aliases where tenant_id=1 and alias='세 번째 프레스'")));
 const u=await card('칸 설정',{type:'설비 점검',op:'단위·설명',prop:'진동',unit:'g',description:'바꾼 설명',old_unit:'mm/s',old_description:'측정한 진동'});await apply(u);
 await undo(u);
 check('unit and description go back',(await one("select unit from property_defs where tenant_id=1 and type_name='설비 점검' and name='진동'")).unit==='mm/s');
 const n=await card('칸 설정',{type:'설비 점검',op:'다른 이름',prop:'진동',alias:'떨림'});await apply(n);
 await undo(n);
 check('other name removed on undo',!(await one("select 1 from alias_dict where tenant_id=1 and type_name='설비 점검' and alias='떨림'")));
 const add=await card('칸 설정',{type:'설비 점검',op:'칸 더하기',name:'습도',dtype:'number'});await apply(add);
 await denied('added column is not undone',()=>undo(add));
 check('undo leaves a trail',(await one("select count(*)::int n from proposals where tenant_id=1 and kind='되돌리기'")).n===4);
}
