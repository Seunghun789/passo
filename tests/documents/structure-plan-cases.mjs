// 011: 워커가 넘긴 구조(payload.structure)가 제안 카드가 되고 정책대로 반영되는지.
export async function structurePlanCases({db,check,uid}) {
 const one=async(sql,args=[])=>(await db.query(sql,args)).rows[0];
 const all=async(sql,args=[])=>(await db.query(sql,args)).rows;
 let seq=950;
 const job=async()=>{
  const sid=(await one("insert into source_inputs(tenant_id,channel,name) values(1,'사진','plan fixture') returning id")).id;
  const id=uid(seq++),fence=uid(seq++);
  await db.query("insert into passo_jobs(id,tenant_id,source_input_id,status,lease_token,lease_until) values($1,1,$2,'running',$3,now()+interval '5 minutes')",[id,sid,fence]);
  return {id,fence,sid};
 };
 const cell=v=>({version:'cell-state-v1',raw:v,value:v,status:'value'});
 const finish=async(j,payload)=>(await one('select public.passo_worker_finish($1,$2,$3) ok',[j.id,j.fence,payload])).ok;
 const prop=(label,name,dtype,extra={})=>({label,name,dtype,unit:null,is_entity:false,ref_class:null,similar_to:null,...extra});
 const records=rows=>rows.map(data=>({type_name:'계획 점검',occurred_at:'2026-11-16',data}));
 const cards=sid=>all('select kind,status,payload,evidence from proposals where source_input_id=$1 order by id',[sid]);

 // 새 종류: 종류 카드가 생기고 정책이 반영해 칸·별칭·기록이 확정된다.
 const a=await job();
 const first={records:records([{'품 목':cell('생수'),'수량(개)':cell('40')},{'품 목':cell('라면'),'수량(개)':cell('12')}]),spans:{},
  structure:{type:'계획 점검',title:'재고 점검표',links:[{from:'품목',to:'수량',kind:'연결',reason:'함께 적힘'}],evidence:{},
   samples:{'품 목':['생수','라면'],'수량(개)':['40','12']},
   props:[prop('품 목','품목','text'),prop('수량(개)','수량','number',{unit:'개'})]}};
 check('structure plan publishes',await finish(a,first));
 const made=await cards(a.sid);
 const type=made.find(q=>q.kind==='종류');
 check('new type becomes an applied type card with AI names',type&&type.status==='승인'&&type.payload.type==='계획 점검'&&type.payload.title==='재고 점검표'&&type.evidence.rows===2&&!('similar_to' in type.payload.props[0]));
 check('type card creates named columns with units',(await one("select unit,dtype from property_defs where tenant_id=1 and type_name='계획 점검' and name='수량'")).unit==='개');
 check('read labels map to column names',(await all("select alias,prop_name from alias_dict where tenant_id=1 and type_name='계획 점검' order by alias")).map(r=>r.alias+'>'+r.prop_name).join()==='수량>수량,수량(개)>수량,품 목>품목,품목>품목');
 check('raw read labels are not registered as columns',(await all("select 1 from property_defs where tenant_id=1 and type_name='계획 점검' and name in ('품 목','수량(개)')")).length===0);
 check('records keep read labels and settle',(await all("select status,data from records where source_input_id=$1",[a.sid])).every(r=>r.status==='확정'&&r.data['수량(개)'].raw));
 check('link from the plan is proposed once the columns exist',made.some(q=>q.kind==='연결'&&q.payload.from==='계획 점검.품목'&&q.payload.to==='계획 점검.수량'));

 // 같은 양식: 아는 칸은 묻지 않고, 새 이름은 같은 칸·새 칸 카드가 된다.
 const b=await job();
 const second={records:records([{'품 목':cell('생수'),'개수':cell('38'),'담당':cell('김')}]),spans:{},
  structure:{type:'계획 점검',title:'재고 점검표',links:[],evidence:{},samples:{'개수':['38'],'담당':['김']},
   props:[prop('품 목','품목','text'),prop('개수','개수','number',{unit:'개',similar_to:'수량'}),prop('담당','담당','text',{similar_to:'없는 칸'})]}};
 check('known type publishes',await finish(b,second));
 const next=await cards(b.sid);
 check('known label is not asked again',!next.some(q=>q.payload.label==='품 목')&&!next.some(q=>q.kind==='종류'));
 const same=next.find(q=>q.kind==='같은 칸');
 check('similar column becomes a same-column card applied by policy',same&&same.payload.similar_to==='수량'&&same.status==='승인'&&(await one("select prop_name from alias_dict where tenant_id=1 and type_name='계획 점검' and alias='개수'")).prop_name==='수량');
 const added=next.find(q=>q.kind==='칸');
 check('unknown target falls back to a new-column card',added&&added.payload.label==='담당'&&!('similar_to' in added.payload)&&(await one("select count(*)::int n from property_defs where tenant_id=1 and type_name='계획 점검' and name='담당'")).n===1);
 check('known-type records settle after structure applies',(await one('select status from records where source_input_id=$1',[b.sid])).status==='확정');

 // AI 없이 올린 구조는 사람이 답할 때까지 기다린다.
 const c=await job();
 const held={records:[{type_name:'손 메모',occurred_at:'2026-11-16',data:{'메모':cell('내일 방문')}}],spans:{},
  structure:{type:'손 메모',title:'손 메모',links:[],evidence:{no_ai:true},samples:{'메모':['내일 방문']},props:[prop('메모','메모','text')]}};
 check('no-AI structure publishes',await finish(c,held));
 check('no-AI type waits for a person and records stay pending',(await cards(c.sid))[0].status==='대기'&&(await one('select status from records where source_input_id=$1',[c.sid])).status==='대기'
  &&(await all("select 1 from object_types where tenant_id=1 and name='손 메모'")).length===0);

 // 잘못된 구조는 전부 되돌린다. 대상 분류 이름과 겹치면 거절한다.
 const d=await job();
 let failed=false;
 try{await finish(d,{...held,structure:{...held.structure,type:''}});}catch(e){failed=e.code==='22023';}
 check('invalid structure rejected atomically',failed&&(await all('select 1 from records where source_input_id=$1',[d.sid])).length===0&&(await one('select status from passo_jobs where id=$1',[d.id])).status==='running');
 await db.exec("insert into object_types(tenant_id,name,kind) values(1,'계획 품목','대상')");
 failed=false;
 try{await finish(d,{...held,structure:{...held.structure,type:'계획 품목'}});}catch(e){failed=true;}
 check('record type cannot reuse an entity class name',failed);

 // 구조가 없는 이전 방식 payload 는 그대로 처리한다.
 check('legacy payload without structure still publishes',await finish(d,{records:[{type_name:'이전 방식',occurred_at:'2026-11-16',data:{'값':cell('1')}}],spans:{}})
  &&(await one("select status from records where source_input_id=$1",[d.sid])).status==='확정');
 const e=await job();
 check('stale worker cannot publish a structure',!(await one('select public.passo_worker_finish($1,$2,$3) ok',[e.id,uid(999),first])).ok);
}
