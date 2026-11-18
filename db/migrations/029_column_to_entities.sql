-- 029: 읽은 값에서 대상 정하기. "칸 설정" 카드에 '대상 칸'(기록 종류의 글 칸을 대상 분류를 가리키는 칸으로)을 더한다.
-- 카드는 core/edits.card 가 확정 지식으로 검사해 만들고(칸의 값 중 아직 대상이 아닌 것), [적용]하면 이 함수가 반영한다.

create or replace function public.passo_user_card_answer(tid bigint, qid bigint, ok boolean) returns jsonb
language plpgsql security definer set search_path='' as $$
declare q public.proposals; p jsonb; cls text; par text; eid bigint; x bigint; y bigint; l public.link_types; k text; v jsonb; n int:=0; dt text;
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 perform 1 from public.tenants where id=tid for update;
 select * into q from public.proposals where id=qid and tenant_id=tid and status='대기' and evidence->>'user'='true' for update;
 if not found then raise exception 'Not found' using errcode='P0002'; end if;
 p:=q.payload;
 if not ok then
  update public.proposals set status='거절',decided_by=passo_private.current_user_id(),decided_at=now() where id=qid;
  return '{"applied":false}';
 end if;

 if q.kind='속성 값' then
  select class_name into cls from public.entities where id=(p->>'entity_id')::bigint and tenant_id=tid;
  if cls is null then raise exception 'Entity missing' using errcode='PT409'; end if;
  -- 정보 칸은 대상의 분류나 그 상위 분류에 있어야 한다
  if not exists(select 1 from public.property_defs d where d.tenant_id=tid and d.name=p->>'attr' and d.type_name in (
    with recursive up(name,depth) as (select cls,0 union all select o.parent_name,up.depth+1 from public.object_types o join up on o.name=up.name
     where o.tenant_id=tid and o.parent_name is not null and up.depth<20) select name from up)) then
   raise exception 'Unknown attribute' using errcode='22023';
  end if;
  update public.entities set attrs=attrs||jsonb_build_object(p->>'attr',p->'new') where id=(p->>'entity_id')::bigint and tenant_id=tid;
 elsif q.kind='대상' then
  perform passo_private.apply_entities(tid,null,jsonb_build_object('entities',(select coalesce(jsonb_agg(jsonb_build_object('class',p->>'class','name',v0)),'[]')
   from jsonb_array_elements_text(coalesce(p->'values','[]')) v0)));
  for k,v in select * from jsonb_each(coalesce(p->'attrs','{}')) loop
   update public.entities set attrs=attrs||v where tenant_id=tid and class_name=p->>'class' and name=btrim(k) and jsonb_typeof(v)='object';
  end loop;
 elsif q.kind='대상 속성' then
  cls:=p->>'class'; dt:=coalesce(p->>'dtype','text');
  if not exists(select 1 from public.object_types where tenant_id=tid and name=cls and kind='대상') or dt not in ('text','number','date','choice')
   or length(coalesce(p->>'attr','')) not between 1 and 100 then raise exception 'Invalid attribute' using errcode='22023'; end if;
  insert into public.property_defs(tenant_id,type_name,name,dtype,unit,position)
  values(tid,cls,btrim(p->>'attr'),dt,nullif(p->>'unit',''),(select count(*) from public.property_defs where tenant_id=tid and type_name=cls))
  on conflict do nothing;
 elsif q.kind='같은 대상' then
  perform passo_private.apply_entities(tid,null,jsonb_build_object('same',jsonb_build_array(jsonb_build_object('class',p->>'class','value',p->>'value','same_as',p->>'same_as','reason',p->>'reason'))));
 elsif q.kind='상위 분류' then
  cls:=btrim(p->>'class'); par:=btrim(p->>'parent');
  if cls is null or par is null or length(cls) not between 1 and 100 or length(par) not between 1 and 100 or cls=par
   or par in (select passo_private.class_tree(tid,cls)) then raise exception 'Class loop' using errcode='22023'; end if;
  if not exists(select 1 from public.object_types where tenant_id=tid and name=par and kind='대상') then
   if exists(select 1 from public.object_types where tenant_id=tid and name=par) then par:=par||' (대상)'; end if;
   insert into public.object_types(tenant_id,name,kind) values(tid,par,'대상') on conflict do nothing;
  end if;
  if exists(select 1 from public.object_types where tenant_id=tid and name=cls and kind='대상') then
   update public.object_types set parent_name=par where tenant_id=tid and name=cls;
  else
   if exists(select 1 from public.object_types where tenant_id=tid and name=cls) then cls:=cls||' (대상)'; end if;
   insert into public.object_types(tenant_id,name,kind,parent_name) values(tid,cls,'대상',par) on conflict do nothing;
  end if;
  for k in select jsonb_array_elements_text(coalesce(p->'members','[]')) loop
   eid:=passo_private.find_in_class(tid,par,k);
   if eid is not null then update public.entities set class_name=cls where id=eid and tenant_id=tid; n:=n+1; end if;
  end loop;
 elsif q.kind='관계 속성' then
  select * into l from public.link_types where id=(p->>'link_id')::bigint and tenant_id=tid for update;
  dt:=coalesce(p->>'dtype','text');
  if not found or position('.' in l.from_ref)>0 or position('.' in l.to_ref)>0 or dt not in ('text','number','date','choice')
   or length(coalesce(p->>'attr','')) not between 1 and 100 then raise exception 'Invalid link attribute' using errcode='22023'; end if;
  if not exists(select 1 from jsonb_array_elements(l.attr_defs) d where d->>'name'=p->>'attr') then
   update public.link_types set attr_defs=attr_defs||jsonb_build_array(jsonb_build_object('name',p->>'attr','dtype',dt)) where id=l.id;
  end if;
  for k,v in select * from jsonb_each(coalesce(p->'values','{}')) loop
   x:=passo_private.find_in_class(tid,l.from_ref,split_part(k,'|',1)); y:=passo_private.find_in_class(tid,l.to_ref,split_part(k,'|',2));
   continue when x is null or y is null;
   insert into public.entity_links(tenant_id,link_id,from_entity,to_entity,attrs) values(tid,l.id,x,y,jsonb_build_object(p->>'attr',v))
   on conflict (tenant_id,link_id,from_entity,to_entity) do update set attrs=public.entity_links.attrs||excluded.attrs;
   n:=n+1;
  end loop;
 elsif q.kind='칸 설정' then
  if not exists(select 1 from public.object_types where tenant_id=tid and name=p->>'type' and kind='기록') then
   raise exception 'Unknown type' using errcode='22023'; end if;
  if p->>'op'='단위·설명' then
   update public.property_defs set unit=nullif(btrim(coalesce(p->>'unit','')),''),description=nullif(btrim(coalesce(p->>'description','')),'')
   where tenant_id=tid and type_name=p->>'type' and name=p->>'prop';
   if not found then raise exception 'Unknown column' using errcode='22023'; end if;
  elsif p->>'op'='다른 이름' then
   if not exists(select 1 from public.property_defs where tenant_id=tid and type_name=p->>'type' and name=p->>'prop')
    or length(coalesce(btrim(p->>'alias'),'')) not between 1 and 200 then raise exception 'Unknown column' using errcode='22023'; end if;
   if exists(select 1 from public.alias_dict where tenant_id=tid and type_name=p->>'type' and alias=btrim(p->>'alias') and prop_name is distinct from p->>'prop') then
    raise exception 'Alias used' using errcode='PT409'; end if;
   insert into public.alias_dict(tenant_id,type_name,alias,prop_name) values(tid,p->>'type',btrim(p->>'alias'),p->>'prop') on conflict do nothing;
  elsif p->>'op'='칸 더하기' then
   dt:=coalesce(p->>'dtype','text');
   if dt not in ('text','number','date','choice') or length(coalesce(btrim(p->>'name'),'')) not between 1 and 100
    or exists(select 1 from public.property_defs where tenant_id=tid and type_name=p->>'type' and name=btrim(p->>'name')) then
    raise exception 'Invalid column' using errcode='22023'; end if;
   insert into public.property_defs(tenant_id,type_name,name,dtype,unit,position)
   values(tid,p->>'type',btrim(p->>'name'),dt,nullif(btrim(coalesce(p->>'unit','')),''),(select count(*) from public.property_defs where tenant_id=tid and type_name=p->>'type'));
   insert into public.alias_dict(tenant_id,type_name,alias,prop_name) values(tid,p->>'type',btrim(p->>'name'),btrim(p->>'name')) on conflict do nothing;
  elsif p->>'op'='대상 칸' then
   -- 기록 종류의 글 칸을 대상 칸으로: 분류가 없으면 만들고, 칸이 그 분류를 가리키게 하고, 칸의 값들을 대상으로 등록한다.
   cls:=btrim(coalesce(p->>'class',''));
   if length(cls) not between 1 and 100 or not exists(select 1 from public.property_defs where tenant_id=tid and type_name=p->>'type'
     and name=p->>'prop' and ref_class is null and dtype in ('text','choice')) then
    raise exception 'Invalid column' using errcode='22023'; end if;
   if exists(select 1 from public.object_types where tenant_id=tid and name=cls and kind<>'대상') then cls:=cls||' (대상)'; end if;
   insert into public.object_types(tenant_id,name,kind) values(tid,cls,'대상') on conflict do nothing;
   update public.property_defs set ref_class=cls where tenant_id=tid and type_name=p->>'type' and name=p->>'prop';
   perform passo_private.apply_entities(tid,null,jsonb_build_object('entities',(select coalesce(jsonb_agg(jsonb_build_object('class',cls,'name',v0)),'[]')
    from jsonb_array_elements_text(coalesce(p->'values','[]')) v0)));
   n:=jsonb_array_length(coalesce(p->'values','[]'));
  else raise exception 'Unknown op' using errcode='22023';
  end if;
 end if;
 update public.proposals set status='승인',decided_by=passo_private.current_user_id(),decided_at=now() where id=qid;
 return jsonb_build_object('applied',true,'count',n);
end $$;
