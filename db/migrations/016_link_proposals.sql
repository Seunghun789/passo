-- 016: 지식그래프의 관계 제안과 [끊기]. 확인하는 사람 이상만 쓴다.
-- [이어 보기](사람이 고른 두 칸)와 [새로 추천받기](AI가 고른 관계)는 '연결' 제안 카드로 올라가고, [맞아요]를 눌러야 이어진다.
-- 카드에는 API 서버가 기록으로 센 근거(counted)가 붙는다. 이미 이어졌거나 기다리는 같은 관계는 다시 올리지 않는다.
begin;

create function public.passo_link_propose(tid bigint, from_ref text, to_ref text, link_kind text, link_name text,
 reason text, counted text, by_user boolean) returns bigint
language plpgsql security definer set search_path='' as $$
declare found_id bigint;
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 if link_kind not in ('연결','함께 움직임','최소 기준','최대 기준','의존','영향','대체') or from_ref=to_ref
  or length(coalesce(from_ref,'')) not between 1 and 300 or length(coalesce(to_ref,'')) not between 1 and 300
  or length(coalesce(link_name,''))>100 or length(coalesce(reason,''))>1000 or length(coalesce(counted,''))>1000 then
  raise exception 'Invalid link' using errcode='22023';
 end if;
 perform pg_advisory_xact_lock(hashtextextended('passo_link:'||tid||':'||from_ref||':'||to_ref||':'||link_kind,0));
 if exists(select 1 from public.link_types l where l.tenant_id=tid and l.from_ref=passo_link_propose.from_ref
   and l.to_ref=passo_link_propose.to_ref and l.kind=link_kind) then
  raise exception 'Already linked' using errcode='PT409';
 end if;
 select q.id into found_id from public.proposals q where q.tenant_id=tid and q.kind='연결' and q.status='대기'
  and q.payload->>'from'=from_ref and q.payload->>'to'=to_ref and q.payload->>'kind'=link_kind limit 1;
 if found_id is not null then return found_id; end if;
 insert into public.proposals(tenant_id,kind,payload,evidence,created_by)
 values(tid,'연결',jsonb_build_object('from',from_ref,'to',to_ref,'kind',link_kind,'name',nullif(btrim(coalesce(link_name,'')),''),
   'reason',case when by_user then '직접 고른 관계예요. ' else '' end||coalesce(reason,'')),
  jsonb_build_object('counted',counted,'user',by_user),passo_private.current_user_id()) returning id into found_id;
 return found_id;
end $$;

create function public.passo_link_cut(tid bigint, link_id bigint) returns void
language plpgsql security definer set search_path='' as $$
declare l public.link_types;
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 select * into l from public.link_types where id=link_id and tenant_id=tid for update;
 if not found then raise exception 'Not found' using errcode='P0002'; end if;
 delete from public.link_types where id=link_id and tenant_id=tid;
 insert into public.proposals(tenant_id,kind,payload,evidence,status,created_by,decided_by,decided_at)
 values(tid,'연결',jsonb_build_object('from',l.from_ref,'to',l.to_ref,'kind',l.kind,'name',l.name,'reason','관계를 끊었어요.'),
  '{"user":true,"cut":true}','거절',passo_private.current_user_id(),passo_private.current_user_id(),now());
end $$;

revoke all on function public.passo_link_propose(bigint,text,text,text,text,text,text,boolean), public.passo_link_cut(bigint,bigint) from public,anon;
grant execute on function public.passo_link_propose(bigint,text,text,text,text,text,text,boolean), public.passo_link_cut(bigint,bigint) to authenticated;
notify pgrst,'reload schema';
commit;
