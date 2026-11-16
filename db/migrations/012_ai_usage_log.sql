-- 012: API 서버가 부른 AI 호출(묻기 등)을 부른 사람의 권한으로 ai_logs 에 남긴다.
begin;

create function public.passo_log_ai(tid bigint,model text,prompt text,answer text,input_tokens integer,output_tokens integer,cost_usd numeric,duration_ms integer)
returns void language plpgsql security definer set search_path='' as $$
begin
 if not public.passo_access(tid,'read') then raise insufficient_privilege; end if;
 if model is null or length(model) not between 1 and 100 or prompt is null or answer is null
 or input_tokens is null or input_tokens not between 0 and 10000000 or output_tokens is null or output_tokens not between 0 and 10000000
 or cost_usd is null or cost_usd<0 or cost_usd>1000 or (duration_ms is not null and duration_ms<0) then
  raise exception 'Invalid usage' using errcode='22023';
 end if;
 insert into public.ai_logs(tenant_id,model,prompt,answer,input_tokens,output_tokens,cost_usd,duration_ms)
 values(tid,model,left(prompt,20000),left(answer,20000),input_tokens,output_tokens,cost_usd,duration_ms);
end $$;

revoke all on function public.passo_log_ai(bigint,text,text,text,integer,integer,numeric,integer) from public,anon;
grant execute on function public.passo_log_ai(bigint,text,text,text,integer,integer,numeric,integer) to authenticated;
notify pgrst,'reload schema';
commit;
