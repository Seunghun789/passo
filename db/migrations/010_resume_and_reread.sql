-- Account-scoped visits and transactional re-extraction of an unconfirmed source.
begin;
create table passo_private.workspace_visits (
 user_id bigint not null references public.users(id) on delete cascade,
 tenant_id bigint not null references public.tenants(id) on delete cascade,
 opened_at timestamptz not null default now(), primary key(user_id,tenant_id)
);
revoke all on passo_private.workspace_visits from public,anon,authenticated;

create function public.passo_open_workspace(tid bigint) returns boolean
language plpgsql security definer set search_path='' as $$
begin
 if not public.passo_access(tid,'read') then raise insufficient_privilege; end if;
 insert into passo_private.workspace_visits(user_id,tenant_id) values(passo_private.current_user_id(),tid)
 on conflict(user_id,tenant_id) do update set opened_at=clock_timestamp();
 return true;
end $$;
create or replace function public.passo_workspaces() returns table(id bigint,title text,role text)
language sql stable security definer set search_path='' as $$
 select t.id,coalesce(t.title,t.name),passo_private.tenant_role(t.id)
 from public.tenants t
 left join passo_private.workspace_visits v on v.tenant_id=t.id and v.user_id=passo_private.current_user_id()
 left join public.memberships m on m.tenant_id=t.id and m.user_id=passo_private.current_user_id()
 where public.passo_access(t.id,'read')
 order by greatest(v.opened_at,m.last_opened_at) desc nulls last,t.id
$$;

alter table public.passo_jobs
 add column model_id text check(model_id in ('claude-haiku-5-5','claude-sonnet-5-5','claude-opus-5-5')),
 add column reread_revision text,
 add column original_bucket text not null default 'passo-originals' check(original_bucket in ('passo-originals','uploads'));
grant select(model_id,reread_revision) on public.passo_jobs to authenticated;

create function public.passo_reread_source(tid bigint,sid bigint,request_key uuid,expected_revision text,
 model text,digest text,mime text,size_bytes bigint) returns public.passo_jobs
language plpgsql security definer set search_path='' as $$
declare s jsonb; j public.passo_jobs; path text; bucket text;
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 if request_key is null or expected_revision is null or expected_revision !~ '^[0-9a-f]{32}$'
 or model is null or model not in ('claude-haiku-5-5','claude-sonnet-5-5','claude-opus-5-5')
 or digest is null or digest !~ '^[0-9a-f]{64}$' or size_bytes is null or size_bytes not between 1 and 4194304
 or mime is null or mime not in ('image/png','image/jpeg','application/pdf') then
  raise exception 'Invalid reread' using errcode='22023';
 end if;
 perform 1 from public.tenants where id=tid for update;
 -- Same advisory lock as upload reservations: a key cannot create two jobs.
 perform pg_advisory_xact_lock(hashtextextended(tid::text||request_key::text,0));
 select * into j from public.passo_jobs where tenant_id=tid and passo_jobs.request_key=passo_reread_source.request_key;
 if found then
  if j.source_input_id<>sid or j.model_id is distinct from model or j.reread_revision is distinct from expected_revision
   or j.sha256<>digest or j.media_type<>mime or j.byte_size<>size_bytes then
   raise exception 'Idempotency key reused' using errcode='PT409';
  end if;
  return j;
 end if;
 perform 1 from public.source_inputs where tenant_id=tid and id=sid for update;
 s:=passo_private.source_snapshot(tid,sid);
 if s is null then raise exception 'Missing source' using errcode='22023'; end if;
 if md5(s::text) is distinct from expected_revision
 or exists(select 1 from public.records where tenant_id=tid and source_input_id=sid and status='확정')
 or exists(select 1 from public.passo_jobs where tenant_id=tid and source_input_id=sid and status in ('uploading','queued','running','awaiting_review')) then
  raise exception 'Source changed, published or busy' using errcode='PT409';
 end if;
 path:=s->'source'->>'storage_path';
 bucket:=case when path ~ ('^uploads/'||tid||'-'||sid||'\.(png|jpg|jpeg|pdf)$') then 'uploads'
  when path ~ ('^'||tid||'/[0-9a-f-]{36}/original\.(png|jpg|pdf)$') then 'passo-originals' end;
 if bucket is null or not exists(select 1 from storage.objects o where o.bucket_id=bucket and o.name=path) then
  raise exception 'Original missing or unbound' using errcode='22023';
 end if;
 insert into public.passo_jobs(tenant_id,source_input_id,status,request_key,sha256,media_type,byte_size,model_id,reread_revision,original_bucket)
 values(tid,sid,'queued',request_key,digest,mime,size_bytes,model,expected_revision,bucket) returning * into j;
 return j;
end $$;

create or replace function public.passo_worker_finish(jid uuid,fence uuid,payload jsonb)
returns boolean language plpgsql security definer set search_path='' as $$
declare j public.passo_jobs; before_value jsonb; qid bigint;
begin
 select * into j from public.passo_jobs where id=jid;
 if not found then return false; end if;
 perform 1 from public.tenants where id=j.tenant_id for update;
 select * into j from public.passo_jobs where id=jid for update;
 if j.status<>'running' or j.lease_token is distinct from fence or j.lease_until<now() then return false; end if;
 if j.reread_revision is null then
  if not passo_private.worker_finish_v1(jid,fence,payload) then return false; end if;
  perform passo_private.auto_apply(j.tenant_id,j.source_input_id);
  return true;
 end if;
 before_value:=passo_private.source_snapshot(j.tenant_id,j.source_input_id);
 if md5(before_value::text) is distinct from j.reread_revision
 or exists(select 1 from public.records where tenant_id=j.tenant_id and source_input_id=j.source_input_id and status='확정') then
  update public.passo_jobs set status='failed',error_code='source_changed',lease_token=null,lease_until=null,updated_at=now() where id=jid;
  return false;
 end if;
 -- Delete/replace only after successful extraction, in this same transaction. Any error rolls back.
 delete from public.proposals where tenant_id=j.tenant_id and source_input_id=j.source_input_id and status='대기';
 delete from public.records where tenant_id=j.tenant_id and source_input_id=j.source_input_id;
 if not passo_private.worker_finish_v1(jid,fence,payload) then raise exception 'Lease changed'; end if;
 update public.records set status='대기' where tenant_id=j.tenant_id and source_input_id=j.source_input_id;
 update public.source_inputs set auto=false where tenant_id=j.tenant_id and id=j.source_input_id;
 update public.proposals q set payload=q.payload||'{"reopened":true}'::jsonb
 where q.tenant_id=j.tenant_id and q.source_input_id=j.source_input_id and q.status='대기';
 insert into public.proposals(tenant_id,kind,payload,evidence,source_input_id)
 values(j.tenant_id,'읽은 값',jsonb_build_object('type',payload->'records'->0->>'type_name',
  'rows',jsonb_array_length(payload->'records'),'reopened',true,'model',j.model_id,'job_id',jid),
  '{"user":true}',j.source_input_id) returning id into qid;
 perform passo_private.audit(j.tenant_id,'원본 다시 읽기',before_value,
  passo_private.source_snapshot(j.tenant_id,j.source_input_id)||jsonb_build_object('job_id',jid,'model',j.model_id));
 return true;
end $$;

-- The old confirmation endpoint must not bypass the new read-review card.
alter function public.passo_confirm_document(bigint,uuid) set schema passo_private;
alter function passo_private.passo_confirm_document(bigint,uuid) rename to confirm_document_v1;
create function public.passo_confirm_document(tid bigint,jid uuid) returns public.passo_jobs
language plpgsql security definer set search_path='' as $$
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 if exists(select 1 from public.passo_jobs where tenant_id=tid and id=jid and reread_revision is not null) then
  raise exception 'Use read review' using errcode='PT409';
 end if;
 return passo_private.confirm_document_v1(tid,jid);
end $$;
revoke all on function passo_private.confirm_document_v1(bigint,uuid) from public,anon,authenticated,service_role;
revoke all on function public.passo_open_workspace(bigint),public.passo_reread_source(bigint,bigint,uuid,text,text,text,text,bigint),public.passo_confirm_document(bigint,uuid) from public,anon;
grant execute on function public.passo_open_workspace(bigint),public.passo_reread_source(bigint,bigint,uuid,text,text,text,text,bigint),public.passo_confirm_document(bigint,uuid) to authenticated;
notify pgrst,'reload schema';
commit;
