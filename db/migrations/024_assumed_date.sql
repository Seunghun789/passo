-- 024: 종이에서 날짜를 읽지 못하면 워커가 올린 날을 기록 날짜로 넣고(payload.date_assumed),
-- 그 종이의 모든 기록을 묶은 "기록 날짜" 애매한 값 카드 하나로 묻는다. 카드에 답하면 기록의 occurred_at 을 고친다.
-- 이 카드는 칸 정의에 없는 이름이라 auto_decision 이 늘 사람에게 남긴다.

create or replace function passo_private.worker_finish_v2(jid uuid, fence uuid, payload jsonb)
returns boolean language plpgsql set search_path='' as $$
declare j public.passo_jobs; s jsonb:=payload->'structure'; t text; r jsonb; p jsonb; l jsonb; n integer:=0; rid bigint; k text; v jsonb;
 known boolean; target text; ev jsonb; a text; b text; ids jsonb:='[]';
begin
 select * into j from public.passo_jobs where id=jid for update;
 if not found or j.status<>'running' or j.lease_token is distinct from fence or j.lease_until<now() then return false; end if;
 if jsonb_typeof(payload->'records') is distinct from 'array' or jsonb_array_length(payload->'records') not between 1 and 1000 then raise exception 'Invalid result'; end if;
 t:=btrim(s->>'type');
 if jsonb_typeof(s->'type') is distinct from 'string' or length(t) not between 1 and 200
 or jsonb_typeof(s->'props') is distinct from 'array' or jsonb_array_length(s->'props')>100
 or jsonb_typeof(coalesce(s->'links','[]')) is distinct from 'array' or jsonb_typeof(coalesce(s->'evidence','{}')) is distinct from 'object' then
  raise exception 'Invalid structure' using errcode='22023';
 end if;
 if exists(select 1 from public.object_types where tenant_id=j.tenant_id and name=t and kind<>'기록') then raise exception 'Type conflicts with entity'; end if;
 known:=exists(select 1 from public.object_types where tenant_id=j.tenant_id and name=t and kind='기록');
 ev:=coalesce(s->'evidence','{}');
 if known then
  for p in select * from jsonb_array_elements(s->'props') loop
   -- 이미 아는 이름이거나 같은 이름을 묻는 카드가 기다리고 있으면 다시 묻지 않는다.
   if exists(select 1 from public.alias_dict where tenant_id=j.tenant_id and type_name=t and alias=p->>'label')
   or exists(select 1 from public.proposals q where q.tenant_id=j.tenant_id and q.status='대기' and q.kind in ('칸','같은 칸') and q.payload->>'type'=t and q.payload->>'label'=p->>'label') then continue; end if;
   target:=p->>'similar_to';
   if target is not null and exists(select 1 from public.property_defs where tenant_id=j.tenant_id and type_name=t and name=target) then
    insert into public.proposals(tenant_id,kind,payload,evidence,source_input_id)
     values(j.tenant_id,'같은 칸',(p-'similar_to')||jsonb_build_object('type',t,'similar_to',target),
      ev||jsonb_build_object('samples',coalesce(s->'samples'->(p->>'label'),'[]')),j.source_input_id);
   else
    insert into public.proposals(tenant_id,kind,payload,evidence,source_input_id)
     values(j.tenant_id,'칸',(p-'similar_to')||jsonb_build_object('type',t),
      ev||jsonb_build_object('samples',coalesce(s->'samples'->(p->>'label'),'[]')),j.source_input_id);
   end if;
  end loop;
  for l in select * from jsonb_array_elements(coalesce(s->'links','[]')) loop
   a:=l->>'from'; b:=l->>'to';
   if l->>'kind' in ('연결','함께 움직임','최소 기준','최대 기준','의존','영향','대체') and a is not null and b is not null and a<>b
    and exists(select 1 from public.property_defs where tenant_id=j.tenant_id and type_name=t and name=a)
    and exists(select 1 from public.property_defs where tenant_id=j.tenant_id and type_name=t and name=b)
    and not exists(select 1 from public.link_types where tenant_id=j.tenant_id and from_ref=t||'.'||a and to_ref=t||'.'||b and kind=l->>'kind')
    and not exists(select 1 from public.proposals q where q.tenant_id=j.tenant_id and q.kind='연결' and q.status='대기' and q.payload->>'from'=t||'.'||a and q.payload->>'to'=t||'.'||b and q.payload->>'kind'=l->>'kind') then
    insert into public.proposals(tenant_id,kind,payload,evidence,source_input_id)
     values(j.tenant_id,'연결',l||jsonb_build_object('from',t||'.'||a,'to',t||'.'||b),'{"user":false}',j.source_input_id);
   end if;
  end loop;
 else
  if jsonb_array_length(s->'props')<1 then raise exception 'Invalid structure' using errcode='22023'; end if;
  insert into public.proposals(tenant_id,kind,payload,evidence,source_input_id)
   values(j.tenant_id,'종류',jsonb_build_object('type',t,'title',coalesce(s->>'title',t),'paper',true,'links',coalesce(s->'links','[]'),
     'props',(select jsonb_agg(x-'similar_to') from jsonb_array_elements(s->'props') x)),
    ev||jsonb_build_object('samples',coalesce(s->'samples','{}'),'rows',jsonb_array_length(payload->'records')),j.source_input_id);
 end if;
 for r in select * from jsonb_array_elements(payload->'records') loop
  insert into public.records(tenant_id,type_name,occurred_at,data,uncertain,source_input_id,source_row,status)
  values(j.tenant_id,t,(r->>'occurred_at')::date,r->'data',coalesce(r->'uncertain','[]'),j.source_input_id,n,'대기') returning id into rid;
  ids:=ids||to_jsonb(rid);
  for k,v in select * from jsonb_each(r->'data') loop
   if v->>'status' in ('ambiguous','unreadable','unknown','missing') or coalesce(r->'uncertain','[]') ? k then
    insert into public.proposals(tenant_id,kind,payload,evidence,source_input_id)
    values(j.tenant_id,'애매한 값',jsonb_build_object('type',t,'label',k,'value',v->'raw','record_id',rid),
      jsonb_build_object('reason',coalesce(v->>'status','uncertain')),j.source_input_id);
   end if;
  end loop;
  n:=n+1;
 end loop;
 if jsonb_typeof(payload->'date_assumed') = 'object' then
  insert into public.proposals(tenant_id,kind,payload,evidence,source_input_id)
  values(j.tenant_id,'애매한 값',jsonb_build_object('type',t,'label','기록 날짜','field','occurred_at',
    'value',payload->'date_assumed'->>'value','record_ids',ids),
   jsonb_build_object('reason','missing','written',coalesce(payload->'date_assumed'->>'written','')),j.source_input_id);
 end if;
 update public.source_inputs set spans=payload->'spans',auto=true where id=j.source_input_id and tenant_id=j.tenant_id;
 update public.passo_jobs set status='succeeded',lease_token=null,lease_until=null,updated_at=now() where id=jid;
 return true;
end $$;

create or replace function passo_private.answer_review_v1(tid bigint, qid bigint, expected_payload jsonb, expected_records jsonb, answer text, value jsonb default null)
returns public.proposals language plpgsql security definer set search_path='' as $$
declare q public.proposals; r public.records; rid bigint; ids jsonb; label text; new_value jsonb; target_status text; day date;
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 select * into q from public.proposals where id=qid and tenant_id=tid for update;
 if not found then raise exception 'Missing review' using errcode='22023'; end if;
 if q.status<>'대기' or q.payload is distinct from expected_payload then raise exception 'Review changed' using errcode='PT409'; end if;
 if answer is null or answer not in ('accept','edit','blank','reject') then raise exception 'Invalid answer' using errcode='22023'; end if;
 if q.kind='애매한 값' and q.payload->>'field'='occurred_at' then
  -- 기록 날짜: 올린 날이 맞으면 그대로 두고, 고치면 그 종이의 기록 날짜를 모두 바꾼다. 날짜는 비울 수 없다.
  if answer not in ('accept','edit') then raise exception 'Supply a date' using errcode='22023'; end if;
  if answer='edit' then
   if jsonb_typeof(value) is distinct from 'string' or value#>>'{}' !~ '^\d{4}-\d{2}-\d{2}$' then raise exception 'Invalid date' using errcode='22023'; end if;
   begin day:=(value#>>'{}')::date; exception when others then raise exception 'Invalid date' using errcode='22023'; end;
  end if;
  ids:=q.payload->'record_ids';
  if jsonb_typeof(ids) is distinct from 'array' or jsonb_array_length(ids) not between 1 and 1000 then raise exception 'Invalid records' using errcode='22023'; end if;
  for rid in select (x#>>'{}')::bigint from jsonb_array_elements(ids) x loop
   select * into r from public.records where id=rid and tenant_id=tid and source_input_id=q.source_input_id for update;
   if not found then raise exception 'Missing record' using errcode='22023'; end if;
   if r.data is distinct from expected_records->rid::text then raise exception 'Record changed' using errcode='PT409'; end if;
   if answer='edit' then update public.records set occurred_at=day where id=rid and tenant_id=tid; end if;
  end loop;
 elsif q.kind='애매한 값' then
  if answer='reject' then raise exception 'Supply corrected value or blank' using errcode='22023'; end if;
  label:=q.payload->>'label';
  ids:=coalesce(q.payload->'record_ids',jsonb_build_array(q.payload->'record_id'));
  if jsonb_typeof(ids) is distinct from 'array' or jsonb_array_length(ids) not between 1 and 1000 then raise exception 'Invalid records' using errcode='22023'; end if;
  for rid in select (x#>>'{}')::bigint from jsonb_array_elements(ids) x loop
   select * into r from public.records where id=rid and tenant_id=tid and source_input_id=q.source_input_id for update;
   if not found or not(r.data ? label) then raise exception 'Missing record' using errcode='22023'; end if;
   if r.data is distinct from expected_records->rid::text then raise exception 'Record changed' using errcode='PT409'; end if;
   if answer in ('edit','blank') then
    new_value:=case when answer='blank' then '""'::jsonb else value end;
    if new_value is null or jsonb_typeof(new_value) not in ('string','number','null') then raise exception 'Invalid value' using errcode='22023'; end if;
    perform passo_private.edit_cells_v1(tid,rid,r.data,jsonb_build_object(label,new_value));
   end if;
   update public.records set uncertain=coalesce((select jsonb_agg(u) from jsonb_array_elements_text(uncertain) u where u<>label),'[]') where id=rid and tenant_id=tid;
  end loop;
 elsif q.kind='연결' then
  if answer not in ('accept','reject') then raise exception 'Invalid link answer' using errcode='22023'; end if;
  if answer='accept' then
   insert into public.link_types(tenant_id,from_ref,to_ref,kind,reason,name)
   values(tid,q.payload->>'from',q.payload->>'to',q.payload->>'kind',q.payload->>'reason',q.payload->>'name')
   on conflict(tenant_id,from_ref,to_ref,kind) do nothing;
  end if;
 else
  raise exception 'This review kind requires the legacy workflow' using errcode='22023';
 end if;
 target_status:=case answer when 'reject' then '거절' when 'edit' then '고침' when 'blank' then '고침' else '승인' end;
 update public.proposals set status=target_status,decided_by=passo_private.current_user_id(),decided_at=now(),
 payload=payload||jsonb_build_object('answer',answer,'answer_value',value) where id=qid and tenant_id=tid returning * into q;
 return q;
end $$;
