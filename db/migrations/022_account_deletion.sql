-- 022: [owner 넘기기] · [계정 지우기] · 1년 지난 AI 기록 · 작업 기록 지우기(예약은 023).
-- 계정을 지우면: 혼자 쓰는 워크스페이스는 기록 · AI 기록과 함께 지우고(AI 기록은 워크스페이스를 따라 지워진다), 원본 파일 경로를 돌려준다(파일은 API 서버가 저장소에서 지운다).
-- 다른 사람과 함께 쓰는 워크스페이스에 남긴 종이 · 기록은 그 워크스페이스의 것이라 남기고, 누가 했는지만 지운다.
-- 다른 구성원이 있는 워크스페이스의 주인이면 지우지 않고, 그 워크스페이스를 돌려준다([owner 넘기기] 먼저).
-- 이 파일은 줄을 지우는 문(delete)이 있어 Supabase SQL 편집기(또는 관리 연결)에서 직접 실행한다.
begin;

-- 워크스페이스를 지우는 중(기록이 함께 지워질 때)에는 바뀐 횟수를 올리지 않는다. 없는 워크스페이스에 숫자를 만들려다 막히지 않게.
create or replace function passo_private.bump_tenant_version() returns trigger
language plpgsql security definer set search_path='' as $$
begin
 if tg_op in ('INSERT','UPDATE') then
  insert into public.tenant_versions as tv (tenant_id, v)
  select distinct c.tenant_id, 1 from changed_new c where c.tenant_id is not null and exists(select 1 from public.tenants t where t.id=c.tenant_id)
  on conflict (tenant_id) do update set v = tv.v + 1;
 end if;
 if tg_op in ('UPDATE','DELETE') then
  insert into public.tenant_versions as tv (tenant_id, v)
  select distinct c.tenant_id, 1 from changed_old c where c.tenant_id is not null and exists(select 1 from public.tenants t where t.id=c.tenant_id)
  on conflict (tenant_id) do update set v = tv.v + 1;
 end if;
 return null;
end $$;
revoke all on function passo_private.bump_tenant_version() from public, anon, authenticated;

-- 워크스페이스를 지우면 그 워크스페이스의 AI 기록(물은 글 · 답 · 읽은 내용)도 함께 지운다. 전에 지운 워크스페이스에서 남은 것도 지운다.
alter table public.ai_logs drop constraint ai_logs_tenant_id_fkey,
 add constraint ai_logs_tenant_id_fkey foreign key (tenant_id) references public.tenants(id) on delete cascade;
delete from public.ai_logs where tenant_id is null;

-- [owner 넘기기]: 주인만, 이 워크스페이스의 다른 구성원에게. 넘긴 사람은 '확인하는 사람'으로 남는다.
-- 조직 주인은 그 조직의 모든 워크스페이스에서 주인이므로, 워크스페이스를 받는 사람의 조직으로 옮긴다(없으면 만든다).
create function public.passo_owner_transfer(tid bigint, member bigint) returns void
language plpgsql security definer set search_path='' as $$
declare me bigint:=passo_private.current_user_id(); oid bigint;
begin
 if me is null or passo_private.tenant_role(tid) is distinct from '주인' then raise insufficient_privilege; end if;
 if member=me then raise exception 'Already owner' using errcode='22023'; end if;
 if not exists(select 1 from public.memberships where tenant_id=tid and user_id=member) then raise exception 'Not found' using errcode='P0002'; end if;
 select org_id into oid from public.org_members where user_id=member and role='주인' order by created_at limit 1;
 if oid is null then
  insert into public.orgs(name) select coalesce(nullif(btrim(t.title),''),'내 워크스페이스') from public.tenants t where t.id=tid returning id into oid;
  insert into public.org_members(org_id,user_id,role) values(oid,member,'주인');
 end if;
 update public.tenants set org_id=oid where id=tid;
 update public.memberships set role='확인하는 사람' where tenant_id=tid and role='주인';
 update public.memberships set role='주인' where tenant_id=tid and user_id=member;
 insert into public.memberships(tenant_id,user_id,role) values(tid,me,'확인하는 사람') on conflict (tenant_id,user_id) do nothing;
end $$;
revoke all on function public.passo_owner_transfer(bigint,bigint) from public,anon;
grant execute on function public.passo_owner_transfer(bigint,bigint) to authenticated;

-- [계정 지우기]. dry_run 이면 지우지 않고 무엇이 지워지는지(혼자 쓰는 워크스페이스)와 막는 것(먼저 넘길 워크스페이스)만 돌려준다.
create function public.passo_delete_me(dry_run boolean default true) returns jsonb
language plpgsql security definer set search_path='' as $$
declare me bigint:=passo_private.current_user_id(); aid uuid:=passo_private.live_auth(); owned bigint[]; alone bigint[]; blocked jsonb; mine jsonb; paths text[];
begin
 if me is null or aid is null then raise insufficient_privilege; end if;
 select coalesce(array_agg(t.id),'{}') into owned from public.tenants t
  where exists(select 1 from public.memberships m where m.tenant_id=t.id and m.user_id=me and m.role='주인')
     or exists(select 1 from public.org_members o where o.org_id=t.org_id and o.user_id=me and o.role='주인');
 alone:=array(select x from unnest(owned) x where not exists(select 1 from public.memberships m where m.tenant_id=x and m.user_id<>me));
 select coalesce(jsonb_agg(jsonb_build_object('id',t.id,'title',t.title) order by t.id),'[]') into blocked
  from public.tenants t where t.id=any(owned) and not t.id=any(alone);
 select coalesce(jsonb_agg(jsonb_build_object('id',t.id,'title',t.title) order by t.id),'[]') into mine
  from public.tenants t where t.id=any(alone);
 if dry_run or jsonb_array_length(blocked)>0 then
  return jsonb_build_object('deleted',false,'blocked',blocked,'workspaces',mine);
 end if;
 select coalesce(array_agg(s.storage_path),'{}') into paths from public.source_inputs s where s.tenant_id=any(alone) and s.storage_path is not null;
 delete from public.tenants where id=any(alone);
 delete from public.orgs o where exists(select 1 from public.org_members m where m.org_id=o.id and m.user_id=me and m.role='주인')
  and not exists(select 1 from public.tenants t where t.org_id=o.id);
 update public.source_inputs set created_by=null where created_by=me;
 update public.proposals set created_by=null where created_by=me;
 update public.proposals set decided_by=null where decided_by=me;
 update public.passo_audit set actor_id=null where actor_id=me;
 update public.passo_audit set undone_by=null where undone_by=me;
 delete from public.invites where created_by=me;
 update public.invites set used_by=null where used_by=me;
 delete from public.users where id=me;  -- 구성원 · 조직 구성원 · 대화 · 연 기록 · 로그인 연결은 함께 지워진다
 delete from auth.users where id=aid;   -- 로그인 계정 · 세션 · 외부 로그인 연결도 함께 지워진다
 return jsonb_build_object('deleted',true,'blocked','[]'::jsonb,'workspaces',mine,'paths',to_jsonb(paths));
end $$;
revoke all on function public.passo_delete_me(boolean) from public,anon;
grant execute on function public.passo_delete_me(boolean) to authenticated;

-- 1년 지난 AI 기록 · 작업 기록 지우기. 023 이 매일 한 번 부른다
create function passo_private.retention() returns void
language sql security definer set search_path='' as $$
 delete from public.ai_logs where created_at < now() - interval '1 year';
 delete from public.passo_audit where created_at < now() - interval '1 year';
$$;
revoke all on function passo_private.retention() from public, anon, authenticated;

notify pgrst, 'reload schema';
commit;
