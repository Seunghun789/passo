-- 020: 구성원 관리의 [내보내기]. 워크스페이스 주인만 하고, 주인 자신은 내보내지 않는다.
-- 내보낸 사람의 워크스페이스 목록에서 그 워크스페이스가 사라진다. 그 사람이 올린 종이와 기록은 워크스페이스에 남는다.
-- 이 파일은 줄을 지우는 문(delete)이 있어 Supabase SQL 편집기에서 직접 실행한다.
begin;

create function public.passo_member_remove(tid bigint, member bigint) returns void
language plpgsql security definer set search_path='' as $$
begin
 if passo_private.tenant_role(tid) is distinct from '주인' then raise insufficient_privilege; end if;
 if member=passo_private.current_user_id() then raise exception 'Cannot remove yourself' using errcode='22023'; end if;
 delete from public.memberships where tenant_id=tid and user_id=member and role<>'주인';
 if not found then raise exception 'Not found' using errcode='P0002'; end if;
end $$;

revoke all on function public.passo_member_remove(bigint,bigint) from public,anon;
grant execute on function public.passo_member_remove(bigint,bigint) to authenticated;
notify pgrst,'reload schema';
commit;
