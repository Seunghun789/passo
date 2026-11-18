-- 027: "읽기에 참고하는 답". 워크스페이스마다 사람이 고친 글씨와 알려 준 뜻을 쌓아, 워커가 다음 사진을 읽을 때
-- 읽기 지시에 함께 보낸다. [지우기]는 removed_at 을 남겨 다음 읽기부터 쓰지 않는다. 다른 워크스페이스에는 쓰지 않는다.

create table public.reading_notes (
  id bigint generated always as identity primary key,
  tenant_id bigint not null references public.tenants(id) on delete cascade,
  kind text not null check (kind in ('고친 글씨','뜻 풀이')),
  label text not null,                       -- 칸 이름
  written text not null default '',          -- AI가 읽은 것(고친 글씨) 또는 적힌 표기(뜻 풀이)
  value text not null default '',            -- 고친 값(빈칸이면 '') 또는 뜻 한 줄
  rule jsonb,                                -- 뜻 풀이를 코드가 쓰는 규칙(다른 이름 · 뽑을 칸)
  proposal_id bigint references public.proposals(id) on delete set null,
  source_input_id bigint references public.source_inputs(id) on delete set null,
  created_at timestamptz not null default now(),
  removed_at timestamptz
);
create index reading_notes_tenant on public.reading_notes(tenant_id, created_at desc) where removed_at is null;
alter table public.reading_notes enable row level security;
create policy passo_read on public.reading_notes for select to authenticated using (tenant_id in (select public.passo_tenant_ids()));
grant select on public.reading_notes to authenticated;
grant select, insert, update on public.reading_notes to service_role;

-- 지금까지 고친 답을 옮겨 둔다.
insert into public.reading_notes(tenant_id,kind,label,written,value,proposal_id,source_input_id,created_at)
select tenant_id,'고친 글씨',payload->>'label',coalesce(payload->>'value',''),coalesce(payload->>'answer_value',''),id,source_input_id,coalesce(decided_at,created_at)
from public.proposals
where kind='애매한 값' and status='고침' and coalesce(payload->>'field','')<>'occurred_at' and payload ? 'label';

create function public.passo_reading_note_remove(tid bigint, nid bigint)
returns boolean language plpgsql security definer set search_path='' as $$
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 update public.reading_notes set removed_at=now() where id=nid and tenant_id=tid and removed_at is null;
 return found;
end $$;
revoke all on function public.passo_reading_note_remove(bigint,bigint) from public,anon;
grant execute on function public.passo_reading_note_remove(bigint,bigint) to authenticated;

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
 -- 고친 글씨는 "읽기에 참고하는 답"에 쌓여 다음 읽기에 함께 간다(기록 날짜 카드는 빼고).
 if q.kind='애매한 값' and target_status='고침' and coalesce(q.payload->>'field','')<>'occurred_at' then
  insert into public.reading_notes(tenant_id,kind,label,written,value,proposal_id,source_input_id)
  values(tid,'고친 글씨',q.payload->>'label',coalesce(q.payload->>'value',''),coalesce(value#>>'{}',''),q.id,q.source_input_id);
 end if;
 return q;
end $$;
