-- 014: 말로 만들기 대화(사람마다 따로)와 AI가 추천한 지표 · 업무 제안. 확인하는 사람 이상만 쓴다.
-- chat_sessions 는 계속 서버 전용 표다. 아래 함수가 부른 사람의 대화만 읽고 쓴다.
-- 지운 대화는 30일 동안 [되돌리기]로 살리고, 그 뒤에는 목록에 나오지 않는다.
begin;

create function public.passo_chats(tid bigint, chat_kind text)
returns table(id bigint, title text, messages jsonb, created_at timestamptz, updated_at timestamptz, deleted_at timestamptz)
language plpgsql stable security definer set search_path='' as $$
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 return query select c.id, c.title, c.messages, c.created_at, c.updated_at, c.deleted_at from public.chat_sessions c
  where c.tenant_id=tid and c.user_id=passo_private.current_user_id() and c.kind=chat_kind
   and (c.deleted_at is null or c.deleted_at > now()-interval '30 days')
  order by c.updated_at desc limit 100;
end $$;

create function public.passo_chat_save(tid bigint, chat_kind text, sid bigint, msgs jsonb) returns bigint
language plpgsql security definer set search_path='' as $$
declare me bigint := passo_private.current_user_id(); out_id bigint;
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 if chat_kind not in ('지표','업무') or jsonb_typeof(msgs)<>'array' or pg_column_size(msgs)>400000 then
  raise exception 'Invalid chat' using errcode='22023';
 end if;
 if sid is null then
  insert into public.chat_sessions(tenant_id,user_id,kind,messages) values(tid,me,chat_kind,msgs) returning id into out_id;
  return out_id;
 end if;
 update public.chat_sessions c set messages=msgs, updated_at=now()
  where c.id=sid and c.tenant_id=tid and c.user_id=me and c.kind=chat_kind and c.deleted_at is null returning c.id into out_id;
 if out_id is null then raise exception 'Not found' using errcode='P0002'; end if;
 return out_id;
end $$;

create function public.passo_chat_update(tid bigint, sid bigint, action text, new_title text default null) returns void
language plpgsql security definer set search_path='' as $$
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 if action not in ('rename','drop','restore') or length(coalesce(new_title,''))>100 then
  raise exception 'Invalid chat action' using errcode='22023';
 end if;
 update public.chat_sessions c set
  title=case when action='rename' then nullif(btrim(new_title),'') else c.title end,
  deleted_at=case action when 'drop' then now() when 'restore' then null else c.deleted_at end,
  updated_at=case when action='restore' then now() else c.updated_at end
 where c.id=sid and c.tenant_id=tid and c.user_id=passo_private.current_user_id()
  and (c.deleted_at is null or c.deleted_at > now()-interval '30 days');
 if not found then raise exception 'Not found' using errcode='P0002'; end if;
end $$;

create function public.passo_rule_propose(tid bigint, rule_kind text, rule jsonb) returns bigint
language plpgsql security definer set search_path='' as $$
declare found bigint;
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 if rule_kind not in ('지표','업무') or not passo_private.valid_rule(rule) then raise exception 'Invalid rule' using errcode='22023'; end if;
 perform pg_advisory_xact_lock(hashtextextended('passo_rule:'||tid||':'||rule_kind||':'||(rule->>'title'),0));
 select q.id into found from public.proposals q
  where q.tenant_id=tid and q.kind=rule_kind and q.status='대기' and q.payload->>'title'=rule->>'title' limit 1;
 if found is not null then return found; end if;
 insert into public.proposals(tenant_id,kind,payload,evidence,created_by)
  values(tid,rule_kind,rule,'{"ai":true}',passo_private.current_user_id()) returning id into found;
 return found;
end $$;

create function public.passo_rule_settle(tid bigint, qid bigint, ok boolean) returns void
language plpgsql security definer set search_path='' as $$
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 update public.proposals set status=case when ok then '승인' else '거절' end,
  decided_by=passo_private.current_user_id(), decided_at=now()
 where id=qid and tenant_id=tid and kind in ('지표','업무') and status='대기';
 if not found then raise exception 'Not found' using errcode='P0002'; end if;
end $$;

revoke all on function public.passo_chats(bigint,text), public.passo_chat_save(bigint,text,bigint,jsonb),
 public.passo_chat_update(bigint,bigint,text,text), public.passo_rule_propose(bigint,text,jsonb),
 public.passo_rule_settle(bigint,bigint,boolean) from public,anon;
grant execute on function public.passo_chats(bigint,text), public.passo_chat_save(bigint,text,bigint,jsonb),
 public.passo_chat_update(bigint,bigint,text,text), public.passo_rule_propose(bigint,text,jsonb),
 public.passo_rule_settle(bigint,bigint,boolean) to authenticated;
notify pgrst,'reload schema';
commit;
