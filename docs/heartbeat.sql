-- CartoonForge heartbeat: GitHub's scheduled workflows are best-effort (often late, sometimes skipped), so
-- Supabase pings the site every 10 minutes and the site starts the publish / render jobs that are due.
-- Run once in Supabase → SQL Editor. No secrets needed (the endpoint only starts jobs, at most every 9 min).
create extension if not exists pg_cron;
create extension if not exists pg_net;
select cron.unschedule(jobid) from cron.job where jobname = 'cartoonforge-heartbeat';
select cron.schedule('cartoonforge-heartbeat', '*/10 * * * *',
  $$ select net.http_post(url := 'https://cartoonforge.vercel.app/api/public/heartbeat',
                          headers := '{"Content-Type": "application/json"}'::jsonb, body := '{}'::jsonb) $$);
select jobname, schedule, active from cron.job where jobname = 'cartoonforge-heartbeat';
