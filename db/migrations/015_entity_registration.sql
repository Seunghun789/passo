-- 015: 읽은 종이에서 대상(품목 · 설비 · 거래처 등)을 등록한다.
-- 워커가 AI · 코드로 정한 대상 계획(payload.entities)을 넘기면, 기록 종류 · 칸이 반영된 바로 뒤 같은 트랜잭션에서 반영한다.
--   classes : 대상을 가리키는 칸을 대상 분류로 잇는다(분류가 없으면 만든다).
--   entities: 처음 보는 대상을 등록한다(이름 자신을 별칭으로).
--   same    : 다르게 적힌 같은 대상을 별칭으로 잇는다(띄어쓰기 · 대소문자만 다르면 코드가, 나머지는 AI가 판단).
-- 반영한 것은 '승인'된 제안 줄로 근거와 함께 남는다. 대상 · 분류 확정 되돌리기는 PRD 비목표다.
-- 같은 함수를 대상 화면의 [새로 추천받기]가 확인하는 사람 권한으로 부른다(passo_entities_apply).
begin;

create function passo_private.apply_entities(tid bigint, sid bigint, plan jsonb) returns jsonb
language plpgsql set search_path='' as $$
declare c jsonb; e jsonb; cls text; nm text; eid bigint; n_class int:=0; n_ent int:=0; n_same int:=0; made jsonb:='[]'; made_in text[]:='{}';
 who bigint:=passo_private.current_user_id();
begin
 if plan is null or jsonb_typeof(plan)<>'object' then return '{"classes":0,"entities":0,"same":0}'; end if;
 if jsonb_typeof(coalesce(plan->'classes','[]'))<>'array' or jsonb_typeof(coalesce(plan->'entities','[]'))<>'array'
  or jsonb_typeof(coalesce(plan->'same','[]'))<>'array' or jsonb_array_length(coalesce(plan->'classes','[]'))>50
  or jsonb_array_length(coalesce(plan->'entities','[]'))>1000 or jsonb_array_length(coalesce(plan->'same','[]'))>1000 then
  raise exception 'Invalid entity plan' using errcode='22023';
 end if;

 for c in select * from jsonb_array_elements(coalesce(plan->'classes','[]')) loop
  cls:=btrim(c->>'class');
  if cls is null or length(cls) not between 1 and 100 then raise exception 'Invalid class' using errcode='22023'; end if;
  -- 확정한 기록 종류의 글 · 고르는 값 칸만 대상을 가리킬 수 있다. 기록 종류와 같은 이름의 분류는 만들지 않는다.
  continue when not exists(select 1 from public.property_defs p join public.object_types o on o.tenant_id=p.tenant_id and o.name=p.type_name and o.kind='기록'
   where p.tenant_id=tid and p.type_name=c->>'type' and p.name=c->>'prop' and p.dtype in ('text','choice'));
  continue when exists(select 1 from public.object_types where tenant_id=tid and name=cls and kind='기록');
  insert into public.object_types(tenant_id,name,kind) values(tid,cls,'대상') on conflict (tenant_id,name) do nothing;
  update public.property_defs set ref_class=cls where tenant_id=tid and type_name=c->>'type' and name=c->>'prop' and ref_class is distinct from cls;
  continue when not found;
  n_class:=n_class+1;
  update public.proposals set status='승인', decided_by=who, decided_at=now()
   where tenant_id=tid and kind='대상 분류' and status='대기' and payload->>'type'=c->>'type' and payload->>'prop'=c->>'prop';
  if not found then
   insert into public.proposals(tenant_id,kind,payload,evidence,status,source_input_id,created_by,decided_by,decided_at)
   values(tid,'대상 분류',jsonb_build_object('type',c->>'type','prop',c->>'prop','class',cls,'values','[]'::jsonb),
    jsonb_build_object('auto',true,'reason',left(coalesce(c->>'reason','대상을 가리키는 칸이에요.'),500)),'승인',sid,who,who,now());
  end if;
 end loop;

 for e in select * from jsonb_array_elements(coalesce(plan->'entities','[]')) loop
  cls:=btrim(e->>'class'); nm:=btrim(e->>'name');
  if cls is null or nm is null or length(nm) not between 1 and 200 then raise exception 'Invalid entity' using errcode='22023'; end if;
  continue when not exists(select 1 from public.object_types where tenant_id=tid and name=cls and kind='대상');
  continue when exists(select 1 from public.entity_aliases a join public.entities x on x.id=a.entity_id
   where a.tenant_id=tid and x.class_name=cls and a.alias=nm);
  insert into public.entities(tenant_id,class_name,name) values(tid,cls,nm) on conflict (tenant_id,class_name,name) do nothing returning id into eid;
  continue when eid is null;
  insert into public.entity_aliases(tenant_id,entity_id,alias) values(tid,eid,nm) on conflict do nothing;
  n_ent:=n_ent+1; made:=made||to_jsonb(nm); made_in:=array_append(made_in,cls);
 end loop;
 if n_ent>0 then
  insert into public.proposals(tenant_id,kind,payload,evidence,status,source_input_id,created_by,decided_by,decided_at)
  values(tid,'대상',jsonb_build_object('values',made,'attrs','{}'::jsonb,'class',(select string_agg(distinct x,', ') from unnest(made_in) x)),
   '{"auto":true,"reason":"처음 보는 대상이에요."}','승인',sid,who,who,now());
 end if;

 for e in select * from jsonb_array_elements(coalesce(plan->'same','[]')) loop
  cls:=btrim(e->>'class'); nm:=btrim(e->>'value');
  if cls is null or nm is null or length(nm) not between 1 and 200 then raise exception 'Invalid alias' using errcode='22023'; end if;
  select x.id into eid from public.entities x where x.tenant_id=tid and x.class_name=cls and x.name=btrim(e->>'same_as');
  continue when eid is null;
  continue when exists(select 1 from public.entity_aliases a join public.entities x on x.id=a.entity_id
   where a.tenant_id=tid and x.class_name=cls and a.alias=nm);
  insert into public.entity_aliases(tenant_id,entity_id,alias) values(tid,eid,nm) on conflict do nothing;
  n_same:=n_same+1;
  insert into public.proposals(tenant_id,kind,payload,evidence,status,source_input_id,created_by,decided_by,decided_at)
  values(tid,'같은 대상',jsonb_build_object('class',cls,'value',nm,'same_as',e->>'same_as','reason',left(coalesce(e->>'reason',''),500)),
   '{"auto":true}','승인',sid,who,who,now());
 end loop;
 return jsonb_build_object('classes',n_class,'entities',n_ent,'same',n_same);
end $$;

-- 워커 반영: 기존 반영(worker_publish_v1)과 자동 반영 뒤에 대상 계획을 같은 트랜잭션에서 반영한다.
alter function passo_private.worker_publish(uuid,uuid,jsonb) rename to worker_publish_v1;
create function passo_private.worker_publish(jid uuid,fence uuid,payload jsonb)
returns boolean language plpgsql set search_path='' as $$
declare j public.passo_jobs;
begin
 select * into j from public.passo_jobs where id=jid;
 if not passo_private.worker_publish_v1(jid,fence,payload) then return false; end if;
 if payload ? 'entities' then
  perform passo_private.auto_apply(j.tenant_id,j.source_input_id);
  perform passo_private.apply_entities(j.tenant_id,j.source_input_id,payload->'entities');
 end if;
 return true;
end $$;

-- 대상 화면 · 지식그래프의 [새로 추천받기]: API 서버가 확정한 기록으로 만든 계획을 확인하는 사람 권한으로 반영한다.
create function public.passo_entities_apply(tid bigint, plan jsonb) returns jsonb
language plpgsql security definer set search_path='' as $$
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 perform 1 from public.tenants where id=tid for update;
 return passo_private.apply_entities(tid,null,plan);
end $$;

revoke all on function passo_private.apply_entities(bigint,bigint,jsonb), passo_private.worker_publish(uuid,uuid,jsonb),
 passo_private.worker_publish_v1(uuid,uuid,jsonb) from public,anon,authenticated;
revoke all on function public.passo_entities_apply(bigint,jsonb) from public,anon;
grant execute on function public.passo_entities_apply(bigint,jsonb) to authenticated;
notify pgrst,'reload schema';
commit;
