-- 028: "뜻 확인". 되풀이되는 짧은 표기(예: '현수 \700')의 뜻을 사람이 [맞아요]나 한 줄 설명으로 확인하면,
-- 규칙(core/meaning.py)으로 푼 값을 새 칸에 넣고 그 뜻을 "읽기에 참고하는 답"(뜻 풀이)에 남긴다.
-- 적힌 글은 원래 칸에 그대로 둔다. 바뀌는 줄은 API가 같은 규칙으로 세어 넘기고, 이 함수는 칸 이름과 값만 검사해 쓴다.

alter table public.proposals drop constraint proposals_kind_check;
alter table public.proposals add constraint proposals_kind_check check (kind in ('종류','칸','같은 칸','애매한 값','연결','지표','업무',
  '대상 분류','대상','같은 대상','대상 속성','속성 값','상위 분류','관계 속성','칸 설정','되돌리기','워크스페이스 설정','읽은 값','맡기기','뜻 확인'));

create function public.passo_apply_meaning(tid bigint, qid bigint, rule jsonb, changes jsonb, said text default null)
returns boolean language plpgsql security definer set search_path='' as $$
declare q public.proposals; t text; label text; cols text[]; col text; rid text; c jsonb; k text; v jsonb; r public.records; h jsonb; n integer:=0;
begin
 if not public.passo_access(tid,'review') then raise insufficient_privilege; end if;
 perform 1 from public.tenants where id=tid for update;
 select * into q from public.proposals where id=qid and tenant_id=tid for update;
 if not found or q.kind<>'뜻 확인' or q.status<>'대기' then raise exception 'Review changed' using errcode='PT409'; end if;
 t:=q.payload->>'type'; label:=q.payload->>'label';
 if jsonb_typeof(rule->'heads') is distinct from 'array' or jsonb_array_length(rule->'heads') not between 1 and 20 then
  raise exception 'Invalid rule' using errcode='22023';
 end if;
 cols:=array_remove(array[nullif(btrim(rule->>'head_col'),''),nullif(btrim(rule->>'number_col'),'')],null);
 if cardinality(cols)=0 then raise exception 'Invalid rule' using errcode='22023'; end if;
 foreach col in array cols loop
  if length(col)>30 or col=label then raise exception 'Invalid column' using errcode='22023'; end if;
  if not exists(select 1 from public.property_defs where tenant_id=tid and type_name=t and name=col) then
   insert into public.property_defs(tenant_id,type_name,name,dtype,position,description)
   values(tid,t,col,case when col=rule->>'number_col' then 'number' else 'text' end,
    coalesce((select max(position)+1 from public.property_defs where tenant_id=tid and type_name=t),0),
    '"'||label||'" 칸에 적힌 표기에서 뽑은 값');
  end if;
 end loop;
 if jsonb_typeof(changes) is distinct from 'object' then raise exception 'Invalid changes' using errcode='22023'; end if;
 for rid,c in select * from jsonb_each(changes) loop
  select * into r from public.records where id=rid::bigint and tenant_id=tid and type_name=t for update;
  if not found or jsonb_typeof(c) is distinct from 'object' then raise exception 'Missing record' using errcode='22023'; end if;
  for k,v in select * from jsonb_each(c) loop
   if not (k = any(cols)) or jsonb_typeof(v) not in ('string','number') then raise exception 'Invalid cell' using errcode='22023'; end if;
   update public.records set data=data||jsonb_build_object(k,jsonb_build_object('version','cell-state-v1','raw',v,'value',v,'status','value'))
   where id=r.id and tenant_id=tid;
  end loop;
  n:=n+1;
 end loop;
 for h in select * from jsonb_array_elements(rule->'heads') loop
  insert into public.reading_notes(tenant_id,kind,label,written,value,rule,proposal_id,source_input_id)
  values(tid,'뜻 풀이',label,h->>'written',
   coalesce(h->>'means','')||coalesce(' · 숫자는 '||nullif(rule->>'number_col',''),''),
   rule||jsonb_build_object('type',t,'label',label),q.id,q.source_input_id);
 end loop;
 update public.proposals set status=case when said is null then '승인' else '고침' end,decided_by=passo_private.current_user_id(),decided_at=now(),
  payload=payload||jsonb_build_object('answer_rule',rule,'said',said,'applied_rows',n) where id=qid and tenant_id=tid;
 perform passo_private.audit(tid,'뜻 풀이 적용',jsonb_build_object('proposal',to_jsonb(q)),jsonb_build_object('rule',rule,'rows',n));
 return true;
end $$;
revoke all on function public.passo_apply_meaning(bigint,bigint,jsonb,jsonb,text) from public,anon;
grant execute on function public.passo_apply_meaning(bigint,bigint,jsonb,jsonb,text) to authenticated;
