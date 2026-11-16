// 015: 워커가 넘긴 대상 계획이 기록 종류 · 칸 반영 바로 뒤에 반영되는지, 대상 화면에서 확인하는 사람만 반영하는지.
export async function entityCases({db,as,denied,check,uid}) {
 const one=async(sql,args=[])=>(await db.query(sql,args)).rows[0];
 const all=async(sql,args=[])=>(await db.query(sql,args)).rows;
 let seq=1200;
 const job=async()=>{
  const sid=(await one("insert into source_inputs(tenant_id,channel,name) values(1,'사진','entity fixture') returning id")).id;
  const id=uid(seq++),fence=uid(seq++);
  await db.query("insert into passo_jobs(id,tenant_id,source_input_id,status,lease_token,lease_until) values($1,1,$2,'running',$3,now()+interval '5 minutes')",[id,sid,fence]);
  return {id,fence,sid};
 };
 const cell=v=>({version:'cell-state-v1',raw:v,value:v,status:'value'});
 const finish=async(j,payload)=>(await one('select public.passo_worker_finish($1,$2,$3) ok',[j.id,j.fence,payload])).ok;
 const prop=(label,name,dtype,extra={})=>({label,name,dtype,unit:null,is_entity:false,ref_class:null,similar_to:null,...extra});
 const structure={type:'설비 점검',title:'설비 점검표',links:[],evidence:{},samples:{},
  props:[prop('설비','설비','text',{is_entity:true}),prop('진동','진동','number')]};
 const rows=data=>data.map(([a,b])=>({type_name:'설비 점검',occurred_at:'2026-11-16',data:{'설비':cell(a),'진동':cell(b)}}));

 const a=await job();
 check('entity plan publishes with the paper',await finish(a,{records:rows([['P-03','6'],['P-07','8']]),spans:{},structure,
  entities:{classes:[{type:'설비 점검',prop:'설비',class:'설비',reason:'주 대상'}],entities:[{class:'설비',name:'P-03'},{class:'설비',name:'P-07'}],same:[]}}));
 check('class is registered right after the new type',(await one("select kind from object_types where tenant_id=1 and name='설비'")).kind==='대상'
  &&(await one("select ref_class from property_defs where tenant_id=1 and type_name='설비 점검' and name='설비'")).ref_class==='설비');
 check('entities and their own names are registered',(await all("select e.name from entities e join entity_aliases a on a.entity_id=e.id and a.alias=e.name where e.tenant_id=1 and e.class_name='설비' order by e.name")).map(r=>r.name).join()==='P-03,P-07');
 const trail=await all('select kind,status,evidence from proposals where source_input_id=$1 and kind in ($2,$3) order by id',[a.sid,'대상 분류','대상']);
 check('applied entity work leaves approved cards with reasons',trail.length===2&&trail.every(q=>q.status==='승인'&&q.evidence.auto===true));

 const b=await job();
 await finish(b,{records:rows([['p 03','5'],['3호 프레스','7'],['P-09','4']]),spans:{},structure,
  entities:{classes:[],entities:[{class:'설비',name:'P-09'}],same:[{class:'설비',value:'p 03',same_as:'P-03',reason:'띄어쓰기만 달라요'},{class:'설비',value:'3호 프레스',same_as:'P-03',reason:'AI'}]}});
 check('differently written names become aliases',(await all("select a.alias from entity_aliases a join entities e on e.id=a.entity_id where e.tenant_id=1 and e.name='P-03' order by a.alias")).map(r=>r.alias).join()==='3호 프레스,P-03,p 03');
 check('new entity on a known type is registered',(await one("select count(*)::int n from entities where tenant_id=1 and class_name='설비' and name='P-09'")).n===1);
 check('same-entity cards are kept as approved',(await all("select 1 from proposals where source_input_id=$1 and kind='같은 대상' and status='승인'",[b.sid])).length===2);

 const c=await job();
 await finish(c,{records:rows([['P-03','6']]),spans:{},structure,entities:{classes:[{type:'설비 점검',prop:'진동',class:'진동 대상'},{type:'없는 종류',prop:'설비',class:'x'}],
  entities:[{class:'없는 분류',name:'z'},{class:'설비',name:'p 03'}],same:[{class:'설비',value:'Q',same_as:'없는 대상'}]}});
 check('number columns and unknown types never become classes',(await all("select 1 from object_types where tenant_id=1 and name in ('진동 대상','x')")).length===0);
 check('unknown class, known alias and unknown target are skipped',(await all("select 1 from entities where tenant_id=1 and name in ('z','p 03')")).length===0
  &&(await all("select 1 from entity_aliases where tenant_id=1 and alias='Q'")).length===0);

 const plan={classes:[],entities:[{class:'설비',name:'P-11'}],same:[]};
 await denied('viewer cannot register entities',()=>as(3,'select public.passo_entities_apply(1,$1)',[plan]));
 await denied('foreign workspace cannot register entities',()=>as(2,'select public.passo_entities_apply(1,$1)',[plan]));
 await denied('oversized plan rejected',()=>as(1,'select public.passo_entities_apply(1,$1)',[{entities:Array.from({length:1001},(_,i)=>({class:'설비',name:'n'+i}))}]));
 const res=(await as(1,'select public.passo_entities_apply(1,$1) r',[plan]))[0].r;
 check('reviewer registers entities from the entity screen',res.entities===1);
 check('B workspace sees none of A entities',(await as(2,'select id from public.entities')).length===0);
 await denied('entities stay read-only for members',()=>as(1,"insert into public.entities(tenant_id,class_name,name) values(1,'설비','직접')"));
}
