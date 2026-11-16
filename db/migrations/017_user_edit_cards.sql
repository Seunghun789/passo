-- 017: 사람이 대상 화면 · 지식그래프에서 직접 고친 것. 바로 쓰지 않고 "직접 고친 것" 카드로 올리고, [적용]을 눌러야 반영한다.
-- 카드 종류: 속성 값(대상 정보 값), 대상(대상 더하기), 대상 속성(정보 더하기), 같은 대상(별칭 더하기),
--           상위 분류(하위 분류로 묶기 · 상위 분류 정하기), 관계 속성(관계 정보), 칸 설정(단위·설명 · 다른 이름 · 칸 더하기).
-- 확인하는 사람 이상만 올리고 반영한다. 반영은 더하거나 고치기만 하고 지우지 않는다.
begin;

create function passo_private.class_tree(tid bigint, root text) returns setof text
language sql stable set search_path='' as $$
 with recursive t(name,depth) as (select root,0 union all
  select o.name,t.depth+1 from public.object_types o join t on o.parent_name=t.name where o.tenant_id=tid and o.kind='대상' and t.depth<20)
 select distinct name from t
$$;

create function passo_private.find_in_class(tid bigint, cls text, nm text) returns bigint
language sql stable set search_path='' as $$
 select x.id from public.entity_aliases a join public.entities x on x.id=a.entity_id
 where a.tenant_id=tid and a.alias=btrim(nm) and x.class_name in (select passo_private.class_tree(tid,cls)) order by x.id limit 1
$$;

create function public.passo_user_card(tid bigint, card_kind text, payload jsonb) returns bigint
language plpgsql security definer set search_path='' as $$
declare out_id bigint;
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 if card_kind not in ('속성 값','대상','대상 속성','같은 대상','상위 분류','관계 속성','칸 설정')
  or jsonb_typeof(payload)<>'object' or pg_column_size(payload)>50000 then
  raise exception 'Invalid card' using errcode='22023';
 end if;
 insert into public.proposals(tenant_id,kind,payload,evidence,created_by)
 values(tid,card_kind,payload,'{"user":true}',passo_private.current_user_id()) returning id into out_id;
 return out_id;
end $$;

create function public.passo_user_card_answer(tid bigint, qid bigint, ok boolean) returns jsonb
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
  else raise exception 'Unknown op' using errcode='22023';
  end if;
 end if;
 update public.proposals set status='승인',decided_by=passo_private.current_user_id(),decided_at=now() where id=qid;
 return jsonb_build_object('applied',true,'count',n);
end $$;

revoke all on function passo_private.class_tree(bigint,text), passo_private.find_in_class(bigint,text,text) from public,anon,authenticated;
revoke all on function public.passo_user_card(bigint,text,jsonb), public.passo_user_card_answer(bigint,bigint,boolean) from public,anon;
grant execute on function public.passo_user_card(bigint,text,jsonb), public.passo_user_card_answer(bigint,bigint,boolean) to authenticated;
notify pgrst,'reload schema';
commit;
