-- 018: 직접 고친 것의 [되돌리기]와 지식그래프의 [끊기]. 확인하는 사람 이상만 쓴다.
-- 되돌릴 수 있는 것: 대상 정보 값(속성 값), 별칭(같은 대상), 칸의 단위·설명, 칸의 다른 이름.
-- 기록 종류 · 칸 · 대상 · 분류 확정은 되돌리지 않는다(PRD 비목표). 되돌린 뒤에 다른 것이 바뀌었으면 되돌리지 않는다.
-- 이 파일은 줄을 지우는 문(delete)이 있어 Supabase SQL 편집기에서 직접 실행한다.
begin;

create or replace function public.passo_link_cut(tid bigint, link_id bigint) returns void
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

create function public.passo_user_card_undo(tid bigint, qid bigint) returns void
language plpgsql security definer set search_path='' as $$
declare q public.proposals; p jsonb; eid bigint; cur jsonb;
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 perform 1 from public.tenants where id=tid for update;
 select * into q from public.proposals where id=qid and tenant_id=tid and status='승인' and evidence->>'user'='true'
  and kind in ('속성 값','같은 대상','칸 설정') and not (payload ? 'undone') for update;
 if not found then raise exception 'Not reversible' using errcode='PT409'; end if;
 p:=q.payload;
 if q.kind='속성 값' then
  select attrs->(p->>'attr') into cur from public.entities where id=(p->>'entity_id')::bigint and tenant_id=tid for update;
  if cur is distinct from p->'new' then raise exception 'Later changes prevent undo' using errcode='PT409'; end if;
  update public.entities set attrs=case when p->'old' is null or p->'old'='null'::jsonb then attrs-(p->>'attr')
   else attrs||jsonb_build_object(p->>'attr',p->'old') end where id=(p->>'entity_id')::bigint and tenant_id=tid;
 elsif q.kind='같은 대상' then
  select x.id into eid from public.entities x where x.tenant_id=tid and x.class_name in (select passo_private.class_tree(tid,p->>'class')) and x.name=p->>'same_as';
  delete from public.entity_aliases where tenant_id=tid and entity_id=eid and alias=btrim(p->>'value');
 elsif p->>'op'='단위·설명' then
  update public.property_defs set unit=p->>'old_unit',description=p->>'old_description' where tenant_id=tid and type_name=p->>'type' and name=p->>'prop';
 elsif p->>'op'='다른 이름' then
  delete from public.alias_dict where tenant_id=tid and type_name=p->>'type' and alias=btrim(p->>'alias') and prop_name=p->>'prop';
 else raise exception 'Not reversible' using errcode='PT409';
 end if;
 update public.proposals set payload=payload||jsonb_build_object('undone',true) where id=qid;
 insert into public.proposals(tenant_id,kind,payload,evidence,status,created_by,decided_by,decided_at)
 values(tid,'되돌리기',jsonb_build_object('of',qid,'kind',q.kind,'was',p),'{"user":true}','승인',
  passo_private.current_user_id(),passo_private.current_user_id(),now());
end $$;

revoke all on function public.passo_link_cut(bigint,bigint), public.passo_user_card_undo(bigint,bigint) from public,anon;
grant execute on function public.passo_link_cut(bigint,bigint), public.passo_user_card_undo(bigint,bigint) to authenticated;
notify pgrst,'reload schema';
commit;
