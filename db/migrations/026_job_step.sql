-- 026: 올리기 화면에 읽는 단계와 읽은 줄 수를 보여 준다. 워커가 체크포인트를 남길 때 job 에 함께 적는다.
-- step: 지금 하는 단계(읽기 · 이어 읽기 · 구조 · 반영). read_rows: 지금까지 읽은 표의 줄 수.

alter table public.passo_jobs add column if not exists step text, add column if not exists read_rows integer;
grant select(step,read_rows) on public.passo_jobs to authenticated;

create or replace function public.passo_worker_save(jid uuid, fence uuid, checkpoint jsonb default null)
returns boolean language plpgsql security definer set search_path='' as $$
declare j public.passo_jobs;
begin
 select * into j from public.passo_jobs where id=jid for update;
 if not found or j.status<>'running' or j.lease_token is distinct from fence or j.lease_until<now() then return false; end if;
 if checkpoint is not null then
  if octet_length(checkpoint::text)>8388608 then raise exception 'Checkpoint too large'; end if;
  insert into public.passo_checkpoints(tenant_id,job_id,revision,state)
  select j.tenant_id,jid,coalesce(max(revision),0)+1,checkpoint from public.passo_checkpoints where job_id=jid;
 end if;
 update public.passo_jobs set lease_until=now()+interval '120 seconds',updated_at=now(),
  step=case when checkpoint is null then step
            when checkpoint ? 'structure' then '반영'
            when checkpoint ? 'fill' then '구조'
            when checkpoint ? 'extraction' then '이어 읽기'
            else '읽기' end,
  read_rows=case when checkpoint is null then read_rows
                 else coalesce(jsonb_array_length(coalesce(checkpoint->'fill'->'sheet'->'rows',checkpoint->'extraction'->'sheet'->'rows')),read_rows) end
 where id=jid;
 return true;
end $$;
