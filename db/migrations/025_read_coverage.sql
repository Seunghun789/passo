-- 025: 하네스가 원본에서 읽지 않은 곳을 센 결과를 종이마다 남긴다(coverage). 워커가 반영할 때 함께 쓴다.
-- coverage: {"unread": 읽지 않은 곳 수, "pages": {"쪽": {"bands": 센 가로줄 수, "unread": [[x0,y0,x1,y1] 0~1000], "read_to": 마지막으로 읽은 가로줄의 아래}}}

alter table public.source_inputs add column if not exists coverage jsonb;

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
 update public.source_inputs set spans=payload->'spans',coverage=payload->'coverage',auto=true where id=j.source_input_id and tenant_id=j.tenant_id;
 update public.passo_jobs set status='succeeded',lease_token=null,lease_until=null,updated_at=now() where id=jid;
 return true;
end $$;
