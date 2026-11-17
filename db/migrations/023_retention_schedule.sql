-- 023: 매일 한국 시각 새벽 3시 30분에 1년 지난 AI 기록 · 작업 기록을 지운다(022 passo_private.retention).
-- Supabase 의 예약 작업 확장(pg_cron)을 켠다. 운영 DB 에서만 실행한다(로컬 시험 DB 에는 이 확장이 없다).
create extension if not exists pg_cron with schema pg_catalog;
grant usage on schema cron to postgres;
select cron.schedule('passo-retention', '30 18 * * *', 'select passo_private.retention()');
