-- CartoonForge schema for Supabase (Postgres + PostgREST). Run once in the Supabase SQL editor.
-- The app talks to these tables with the service key (server and GitHub worker only; never the browser),
-- so Row Level Security is enabled with no public policies.
-- Timestamps are ISO strings written by the app (text sorts correctly for ISO-8601 UTC).
-- Every table has an `extra` jsonb column: fields without their own column are kept there by the app.
-- Safe to run again: it only adds what is missing.

create table if not exists episodes (
  id text primary key,
  created_at text default to_char(now() at time zone 'utc', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"'),
  updated_at text,
  kind text default 'episode',
  status text,
  category text,
  topic text,
  age_band text,
  language text,
  minutes double precision,
  duration double precision,
  variant jsonb,
  why text,
  angle text,
  source jsonb,
  editions jsonb,
  progress jsonb,
  error text,
  script jsonb,
  critic jsonb,
  safety jsonb,
  meta jsonb,
  video_url text,
  thumb_url text,
  timeline jsonb,
  song_regions jsonb,
  qa jsonb,
  engines jsonb,
  rendered_at text,
  publish_at text,
  published_at text,
  youtube jsonb,
  stats jsonb,
  parent_id text,
  edition_of text,
  -- Step 16
  art_style text,
  animation text,
  ai_budget_usd double precision,
  ai_video jsonb,
  rendered_style text
);
create index if not exists episodes_status on episodes (status);
create index if not exists episodes_created on episodes (created_at desc);

create table if not exists events (
  id text primary key,
  created_at text default to_char(now() at time zone 'utc', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"'),
  updated_at text,
  level text,
  msg text,
  episode_id text
);
create index if not exists events_created on events (created_at desc);
create index if not exists events_episode on events (episode_id);

create table if not exists settings (
  id text primary key,
  created_at text default to_char(now() at time zone 'utc', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"'),
  updated_at text,
  value jsonb
);

create table if not exists topics (
  id text primary key,
  created_at text default to_char(now() at time zone 'utc', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"'),
  updated_at text,
  topic text,
  category text,
  episode_id text
);

create table if not exists trends (
  id text primary key,
  created_at text default to_char(now() at time zone 'utc', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"'),
  updated_at text,
  topic text,
  category text,
  age_band text,
  score double precision,
  used boolean default false,
  why text,
  angle text,
  episode_id text
);

-- Step 16: the story cast library
create table if not exists characters (
  id text primary key,
  created_at text default to_char(now() at time zone 'utc', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"'),
  updated_at text,
  tier text default 'cameo',
  name text,
  kind text,
  species text,
  gender text,
  age text,
  colors jsonb,
  outfit text,
  skin text,
  hair text,
  hair_color text,
  personality text,
  look text,
  catchphrase text,
  voice text,
  pitch double precision,
  origin jsonb,
  episodes jsonb default '[]'::jsonb
);

-- Parent / viewer feedback (public form, linked from every video description)
create table if not exists feedback (
  id text primary key,
  created_at text default to_char(now() at time zone 'utc', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"'),
  updated_at text,
  episode_id text,
  enjoyed text,
  style integer,
  animation integer,
  voices integer,
  learning integer,
  change text,
  request text,
  age_band text,
  role text
);
create index if not exists feedback_episode on feedback (episode_id);

alter table episodes add column if not exists extra jsonb default '{}'::jsonb;
alter table events add column if not exists extra jsonb default '{}'::jsonb;
alter table settings add column if not exists extra jsonb default '{}'::jsonb;
alter table topics add column if not exists extra jsonb default '{}'::jsonb;
alter table trends add column if not exists extra jsonb default '{}'::jsonb;
alter table characters add column if not exists extra jsonb default '{}'::jsonb;
alter table feedback add column if not exists extra jsonb default '{}'::jsonb;

alter table episodes enable row level security;
alter table events enable row level security;
alter table settings enable row level security;
alter table topics enable row level security;
alter table trends enable row level security;
alter table characters enable row level security;
alter table feedback enable row level security;

-- Storage: create a PUBLIC bucket named "episodes" (Storage → New bucket), or:
insert into storage.buckets (id, name, public) values ('episodes', 'episodes', true) on conflict (id) do nothing;
