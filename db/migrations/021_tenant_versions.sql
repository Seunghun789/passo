-- 021: 워크스페이스마다 확정 지식(기록 종류 · 칸 · 별칭 · 관계 · 대상 · 기록)이 바뀐 횟수.
-- API 서버는 이 숫자 하나만 읽어 보고, 그대로면 읽어 둔 표를 다시 쓴다. 워커 · DB 함수 · 사람이 쓴 것 모두 여기 센다.
begin;

create table public.tenant_versions (
 tenant_id bigint primary key references public.tenants(id) on delete cascade,
 v bigint not null default 0
);
alter table public.tenant_versions enable row level security;
create policy passo_read on public.tenant_versions for select to authenticated
 using (tenant_id in (select public.passo_tenant_ids()));
revoke all on public.tenant_versions from public, anon, authenticated;
grant select on public.tenant_versions to authenticated;

create function passo_private.bump_tenant_version() returns trigger
language plpgsql security definer set search_path='' as $$
begin
 if tg_op in ('INSERT','UPDATE') then
  insert into public.tenant_versions as tv (tenant_id, v) select distinct tenant_id, 1 from changed_new where tenant_id is not null
  on conflict (tenant_id) do update set v = tv.v + 1;
 end if;
 if tg_op in ('UPDATE','DELETE') then
  insert into public.tenant_versions as tv (tenant_id, v) select distinct tenant_id, 1 from changed_old where tenant_id is not null
  on conflict (tenant_id) do update set v = tv.v + 1;
 end if;
 return null;
end $$;
revoke all on function passo_private.bump_tenant_version() from public, anon, authenticated;

do $$
declare t text;
begin
 foreach t in array array['object_types','alias_dict','link_types','records','entities','entity_links','property_defs','entity_aliases'] loop
  execute format('create trigger passo_version_ins after insert on public.%I referencing new table as changed_new for each statement execute function passo_private.bump_tenant_version()', t);
  execute format('create trigger passo_version_upd after update on public.%I referencing new table as changed_new old table as changed_old for each statement execute function passo_private.bump_tenant_version()', t);
  execute format('create trigger passo_version_del after delete on public.%I referencing old table as changed_old for each statement execute function passo_private.bump_tenant_version()', t);
 end loop;
end $$;

insert into public.tenant_versions (tenant_id, v) select id, 0 from public.tenants on conflict do nothing;

notify pgrst, 'reload schema';
commit;
