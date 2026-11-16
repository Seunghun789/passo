-- 019: 가입 · 워크스페이스 생성 · 초대 · 구성원 · 내 계정 · 워크스페이스 정보.
-- 가입: Supabase Auth 로 로그인한 사람(살아 있는 세션)을 passo 사람(public.users)에 잇는다.
--   이메일 가입은 메일 확인을 마친 뒤에만 잇고, 같은 이메일로 예전에 가입한 사람이 있으면 그 사람(기록 · 워크스페이스)에 잇는다.
--   Google · 카카오는 그 공급자의 고유 번호(provider_id)로 잇는다. 이메일만 같다고 다른 공급자 계정에 잇지 않는다.
-- 줄을 지우는 일([내보내기])은 이 파일에 없다.
begin;

create function passo_private.live_auth() returns uuid
language sql stable security definer set search_path='' as $$
 select u.id from auth.users u join auth.sessions s on s.user_id=u.id
 where u.id=auth.uid() and s.id::text=auth.jwt()->>'session_id' and (s.not_after is null or s.not_after>now())
  and (u.banned_until is null or u.banned_until<now()) and coalesce((auth.jwt()->>'exp')::numeric,0)>extract(epoch from now())
$$;

create function public.passo_register_self(display_name text default null) returns boolean
language plpgsql security definer set search_path='' as $$
declare aid uuid:=passo_private.live_auth(); a auth.users; prov text; subject text; lid bigint; nm text;
begin
 if aid is null then raise insufficient_privilege; end if;
 if exists(select 1 from public.auth_identity_links where auth_user_id=aid) then return true; end if;
 select * into a from auth.users where id=aid;
 prov:=coalesce(auth.jwt()->'app_metadata'->>'provider','email');
 if prov='email' then
  if a.email is null or a.email_confirmed_at is null then return false; end if;  -- 메일 확인 전에는 잇지 않는다
  subject:=lower(btrim(a.email));
 elsif prov in ('google','kakao') then
  select i.provider_id into subject from auth.identities i where i.user_id=aid and i.provider=prov limit 1;
  if subject is null then return false; end if;
 else return false;
 end if;
 nm:=left(coalesce(nullif(btrim(display_name),''),a.raw_user_meta_data->>'full_name',a.raw_user_meta_data->>'name',split_part(coalesce(a.email,''),'@',1),'새 사용자'),60);
 select u.id into lid from public.users u where u.provider=prov and (u.sub=subject or (prov='email' and lower(btrim(u.sub))=subject)) order by u.id limit 1;
 if lid is null then
  insert into public.users(provider,sub,name,email) values(prov,subject,nm,a.email) on conflict (provider,sub) do nothing returning id into lid;
  if lid is null then select u.id into lid from public.users u where u.provider=prov and u.sub=subject; end if;
 end if;
 insert into public.auth_identity_links(auth_user_id,legacy_user_id) values(aid,lid) on conflict do nothing;
 return exists(select 1 from public.auth_identity_links where auth_user_id=aid and legacy_user_id=lid);
end $$;

create function public.passo_workspace_create(new_title text) returns bigint
language plpgsql security definer set search_path='' as $$
declare me bigint:=passo_private.current_user_id(); oid bigint; tid bigint; t text:=left(btrim(coalesce(new_title,'')),60);
begin
 if me is null then raise insufficient_privilege; end if;
 if t='' then t:='내 워크스페이스'; end if;
 if (select count(*) from public.memberships where user_id=me and role='주인')>=20 then raise exception 'Too many workspaces' using errcode='22023'; end if;
 select org_id into oid from public.org_members where user_id=me and role='주인' order by created_at limit 1;
 if oid is null then
  insert into public.orgs(name) values(t) returning id into oid;
  insert into public.org_members(org_id,user_id,role) values(oid,me,'주인');
 end if;
 insert into public.tenants(name,title,org_id) values('ws-'||replace(gen_random_uuid()::text,'-',''),t,oid) returning id into tid;
 insert into public.memberships(tenant_id,user_id,role,last_opened_at) values(tid,me,'주인',now());
 return tid;
end $$;

create function public.passo_me() returns table(name text, email text, phone text, provider text)
language sql stable security definer set search_path='' as $$
 select u.name,u.email,u.phone,u.provider from public.users u where u.id=passo_private.current_user_id()
$$;

create function public.passo_me_update(new_name text, new_email text, new_phone text) returns void
language plpgsql security definer set search_path='' as $$
declare me bigint:=passo_private.current_user_id();
begin
 if me is null then raise insufficient_privilege; end if;
 if length(btrim(coalesce(new_name,''))) not between 1 and 60 or length(coalesce(new_email,''))>254 or length(coalesce(new_phone,''))>30
  or (coalesce(new_email,'')<>'' and new_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$') or (coalesce(new_phone,'')<>'' and new_phone !~ '^[0-9+() -]{6,30}$') then
  raise exception 'Invalid account' using errcode='22023';
 end if;
 update public.users set name=btrim(new_name),email=nullif(btrim(coalesce(new_email,'')),''),phone=nullif(btrim(coalesce(new_phone,'')),'') where id=me;
end $$;

create function public.passo_workspace_info(tid bigint) returns jsonb
language plpgsql stable security definer set search_path='' as $$
declare t public.tenants; o public.orgs;
begin
 if not public.passo_access(tid,'read') then raise insufficient_privilege; end if;
 select * into t from public.tenants where id=tid; select * into o from public.orgs where id=t.org_id;
 return jsonb_build_object('title',t.title,'about',t.about,'org',o.name,'industry',o.industry,'product',o.product,'website',o.website,
  'role',passo_private.tenant_role(tid),'org_owner',exists(select 1 from public.org_members m where m.org_id=t.org_id and m.user_id=passo_private.current_user_id() and m.role='주인'));
end $$;

create function public.passo_workspace_update(tid bigint, new_title text, new_about text, org_name text, org_industry text, org_product text, org_website text)
returns void language plpgsql security definer set search_path='' as $$
begin
 if passo_private.tenant_role(tid) is distinct from '주인' then raise insufficient_privilege; end if;
 if length(btrim(coalesce(new_title,''))) not between 1 and 60 or length(coalesce(new_about,''))>500 or length(coalesce(org_name,''))>100
  or length(coalesce(org_industry,''))>100 or length(coalesce(org_product,''))>200 or length(coalesce(org_website,''))>300 then
  raise exception 'Invalid workspace' using errcode='22023';
 end if;
 update public.tenants set title=btrim(new_title),about=nullif(btrim(coalesce(new_about,'')),'') where id=tid;
 update public.orgs o set name=coalesce(nullif(btrim(coalesce(org_name,'')),''),o.name),industry=nullif(btrim(coalesce(org_industry,'')),''),
  product=nullif(btrim(coalesce(org_product,'')),''),website=nullif(btrim(coalesce(org_website,'')),'')
 where o.id=(select org_id from public.tenants where id=tid)
  and exists(select 1 from public.org_members m where m.org_id=o.id and m.user_id=passo_private.current_user_id() and m.role='주인');
end $$;

create function public.passo_members(tid bigint) returns table(user_id bigint, name text, email text, role text, me boolean, last_opened_at timestamptz)
language plpgsql stable security definer set search_path='' as $$
declare owner boolean:=passo_private.tenant_role(tid)='주인';
begin
 if not public.passo_access(tid,'read') then raise insufficient_privilege; end if;
 return query select u.id,u.name,case when owner or u.id=passo_private.current_user_id() then u.email end,m.role,
  u.id=passo_private.current_user_id(),m.last_opened_at
  from public.memberships m join public.users u on u.id=m.user_id where m.tenant_id=tid
  order by m.role='주인' desc, m.created_at;
end $$;

create function public.passo_member_role(tid bigint, member bigint, new_role text) returns void
language plpgsql security definer set search_path='' as $$
begin
 if passo_private.tenant_role(tid) is distinct from '주인' then raise insufficient_privilege; end if;
 if new_role not in ('확인하는 사람','올리는 사람','보는 사람') then raise exception 'Invalid role' using errcode='22023'; end if;
 update public.memberships set role=new_role where tenant_id=tid and user_id=member and role<>'주인';
 if not found then raise exception 'Not found' using errcode='P0002'; end if;
end $$;

create function public.passo_invite_create(tid bigint, invite_role text) returns text
language plpgsql security definer set search_path='' as $$
declare tok text:=replace(gen_random_uuid()::text,'-','')||replace(gen_random_uuid()::text,'-','');
begin
 if passo_private.tenant_role(tid) is distinct from '주인' then raise insufficient_privilege; end if;
 if invite_role not in ('확인하는 사람','올리는 사람','보는 사람') then raise exception 'Invalid role' using errcode='22023'; end if;
 if (select count(*) from public.invites where tenant_id=tid and used_by is null and expires_at>now())>=50 then raise exception 'Too many invites' using errcode='22023'; end if;
 insert into public.invites(token,tenant_id,role,created_by) values(tok,tid,invite_role,passo_private.current_user_id());
 return tok;
end $$;

create function public.passo_invites(tid bigint) returns table(token text, role text, expires_at timestamptz, used_by text, created_at timestamptz)
language plpgsql stable security definer set search_path='' as $$
begin
 if passo_private.tenant_role(tid) is distinct from '주인' then raise insufficient_privilege; end if;
 return query select i.token,i.role,i.expires_at,u.name,i.created_at from public.invites i left join public.users u on u.id=i.used_by
  where i.tenant_id=tid order by i.created_at desc limit 50;
end $$;

-- 초대 링크를 연 사람에게 보이는 것: 워크스페이스 이름 · 역할 · 쓸 수 있는지. 토큰이 맞아야만 보인다.
create function public.passo_invite_preview(tok text) returns jsonb
language sql stable security definer set search_path='' as $$
 select jsonb_build_object('title',coalesce(t.title,'워크스페이스'),'role',i.role,'valid',i.used_by is null and i.expires_at>now())
 from public.invites i join public.tenants t on t.id=i.tenant_id where i.token=tok and length(tok)=64
$$;

create function public.passo_invite_accept(tok text) returns bigint
language plpgsql security definer set search_path='' as $$
declare me bigint:=passo_private.current_user_id(); i public.invites;
begin
 if me is null then raise insufficient_privilege; end if;
 select * into i from public.invites where token=tok and length(tok)=64 for update;
 if not found or i.used_by is not null or i.expires_at<=now() then raise exception 'Invite expired' using errcode='PT409'; end if;
 insert into public.memberships(tenant_id,user_id,role,last_opened_at) values(i.tenant_id,me,i.role,now()) on conflict (tenant_id,user_id) do nothing;
 update public.invites set used_by=me where token=tok;
 return i.tenant_id;
end $$;

revoke all on function passo_private.live_auth() from public,anon,authenticated;
revoke all on function public.passo_register_self(text), public.passo_workspace_create(text), public.passo_me(), public.passo_me_update(text,text,text),
 public.passo_workspace_info(bigint), public.passo_workspace_update(bigint,text,text,text,text,text,text), public.passo_members(bigint),
 public.passo_member_role(bigint,bigint,text), public.passo_invite_create(bigint,text), public.passo_invites(bigint),
 public.passo_invite_preview(text), public.passo_invite_accept(text) from public,anon;
grant execute on function public.passo_register_self(text), public.passo_workspace_create(text), public.passo_me(), public.passo_me_update(text,text,text),
 public.passo_workspace_info(bigint), public.passo_workspace_update(bigint,text,text,text,text,text,text), public.passo_members(bigint),
 public.passo_member_role(bigint,bigint,text), public.passo_invite_create(bigint,text), public.passo_invites(bigint),
 public.passo_invite_preview(text), public.passo_invite_accept(text) to authenticated;
notify pgrst,'reload schema';
commit;
