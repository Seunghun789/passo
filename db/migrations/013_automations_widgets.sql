-- 013: 자동화 [켜기]·[끄기]·[다시 켜기], 지표 [올리기]·[내리기]. 확인하는 사람 이상만 쓴다.
-- 규칙(rule)은 API 서버가 확정 지식에서 다시 만든 것을 넘긴다. 같은 제목이 이미 있으면 새로 넣지 않고 그 줄을 켠다.
begin;

create function passo_private.valid_rule(spec jsonb) returns boolean
language sql immutable set search_path='' as $$
 select coalesce(jsonb_typeof(spec)='object' and pg_column_size(spec)<=20000
  and jsonb_typeof(spec->'title')='string' and length(spec->>'title') between 1 and 200
  and jsonb_typeof(spec->'type')='string' and length(spec->>'type') between 1 and 200
  and coalesce(jsonb_typeof(spec->'conditions'),'array')='array',false)
$$;

create function public.passo_automation_add(tid bigint, rule jsonb) returns bigint
language plpgsql security definer set search_path='' as $$
declare found bigint;
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 if not passo_private.valid_rule(rule) then raise exception 'Invalid rule' using errcode='22023'; end if;
 perform pg_advisory_xact_lock(hashtextextended('passo_automation:'||tid||':'||(rule->>'title'),0));
 select a.id into found from public.automations a where a.tenant_id=tid and a.spec->>'title'=rule->>'title' order by a.id limit 1;
 if found is not null then
  update public.automations set status='켜짐' where id=found;
  return found;
 end if;
 insert into public.automations(tenant_id,spec) values(tid,rule) returning id into found;
 return found;
end $$;

create function public.passo_automation_status(tid bigint, aid bigint, next_status text) returns void
language plpgsql security definer set search_path='' as $$
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 if next_status not in ('켜짐','꺼짐') then raise exception 'Invalid status' using errcode='22023'; end if;
 update public.automations set status=next_status where id=aid and tenant_id=tid;
 if not found then raise exception 'Not found' using errcode='P0002'; end if;
end $$;

create function public.passo_widget_add(tid bigint, rule jsonb) returns bigint
language plpgsql security definer set search_path='' as $$
declare found bigint;
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 if not passo_private.valid_rule(rule) then raise exception 'Invalid rule' using errcode='22023'; end if;
 perform pg_advisory_xact_lock(hashtextextended('passo_widget:'||tid||':'||(rule->>'title'),0));
 select w.id into found from public.widgets w where w.tenant_id=tid and w.spec->>'title'=rule->>'title' order by w.id limit 1;
 if found is not null then
  update public.widgets set status='올림' where id=found;
  return found;
 end if;
 insert into public.widgets(tenant_id,spec) values(tid,rule) returning id into found;
 return found;
end $$;

create function public.passo_widget_status(tid bigint, wid bigint, next_status text) returns void
language plpgsql security definer set search_path='' as $$
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 if next_status not in ('올림','내림') then raise exception 'Invalid status' using errcode='22023'; end if;
 update public.widgets set status=next_status where id=wid and tenant_id=tid;
 if not found then raise exception 'Not found' using errcode='P0002'; end if;
end $$;

revoke all on function passo_private.valid_rule(jsonb) from public,anon,authenticated;
revoke all on function public.passo_automation_add(bigint,jsonb), public.passo_automation_status(bigint,bigint,text),
 public.passo_widget_add(bigint,jsonb), public.passo_widget_status(bigint,bigint,text) from public,anon;
grant execute on function public.passo_automation_add(bigint,jsonb), public.passo_automation_status(bigint,bigint,text),
 public.passo_widget_add(bigint,jsonb), public.passo_widget_status(bigint,bigint,text) to authenticated;
notify pgrst,'reload schema';
commit;
