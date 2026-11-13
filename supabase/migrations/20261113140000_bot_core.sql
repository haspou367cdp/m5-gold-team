-- Applied to project m5-gold-bot (kinbkthbbwzrfogqqttl) via the Supabase MCP. Kept here as the source of record.
create extension if not exists pg_cron;
create extension if not exists pg_net;

create table if not exists public.bot_state (
  id int primary key default 1 check (id = 1),
  state jsonb not null default '{}'::jsonb,
  news jsonb,
  version bigint not null default 0,
  updated_at timestamptz not null default now()
);
alter table public.bot_state enable row level security;  -- no policies: only service_role (Edge Function) can touch it
insert into public.bot_state (id) values (1) on conflict do nothing;
revoke all on public.bot_state from anon, authenticated;

create or replace function public.bot_secret(p_name text) returns text
language sql stable security definer set search_path = '' as $$
  select decrypted_secret from vault.decrypted_secrets where name = p_name limit 1
$$;
create or replace function public.bot_set_secret(p_name text, p_value text) returns void
language plpgsql security definer set search_path = '' as $$
declare sid uuid;
begin
  if p_value is null or length(p_value) < 10 then raise exception 'bad secret'; end if;
  select id into sid from vault.secrets where name = p_name;
  if sid is null then perform vault.create_secret(p_value, p_name);
  else perform vault.update_secret(sid, p_value); end if;
end $$;
create or replace function public.bot_webhook_secret() returns text
language plpgsql security definer set search_path = '' as $$
declare s text;
begin
  select decrypted_secret into s from vault.decrypted_secrets where name = 'tg_webhook_secret';
  if s is null then
    s := encode(extensions.gen_random_bytes(32), 'hex');
    perform vault.create_secret(s, 'tg_webhook_secret');
  end if;
  return s;
end $$;
create or replace function public.bot_save(p_state jsonb, p_version bigint) returns boolean
language plpgsql security definer set search_path = '' as $$
begin
  update public.bot_state set state = p_state, version = version + 1, updated_at = now()
   where id = 1 and version = p_version;
  return found;
end $$;
create or replace function public.bot_merge(p_patch jsonb, p_done jsonb, p_news jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare allowed text[] := array['signals_sent','presession_sent','last_run_tehran','last_verdict','news_fetched_at'];
        clean jsonb; r jsonb;
begin
  select coalesce(jsonb_object_agg(key, value), '{}'::jsonb) into clean
    from jsonb_each(coalesce(p_patch, '{}'::jsonb)) where key = any(allowed);
  update public.bot_state set
    state = jsonb_set(state || clean, '{pending_cmds}', (
      select coalesce(jsonb_agg(x), '[]'::jsonb) from jsonb_array_elements(coalesce(state->'pending_cmds', '[]'::jsonb)) x
       where not (coalesce(p_done, '[]'::jsonb) @> jsonb_build_array(x->'id')))),
    news = coalesce(p_news, news), version = version + 1, updated_at = now()
   where id = 1 returning jsonb_build_object('pending', jsonb_array_length(state->'pending_cmds'), 'version', version) into r;
  return r;
end $$;
create or replace function public.bot_dispatch(p_mode text) returns bigint
language plpgsql security definer set search_path = '' as $$
declare tok text := public.bot_secret('gh_dispatch_token');
begin
  if tok is null then return null; end if;
  return net.http_post(
    url := 'https://api.github.com/repos/haspou367cdp/m5-gold-team/actions/workflows/telegram-bot.yml/dispatches',
    body := jsonb_build_object('ref', 'main', 'inputs', jsonb_build_object('mode', p_mode)),
    headers := jsonb_build_object('Authorization', 'Bearer ' || tok, 'Accept', 'application/vnd.github+json',
                                  'User-Agent', 'm5-gold-bot', 'X-GitHub-Api-Version', '2022-11-28',
                                  'Content-Type', 'application/json'),
    timeout_milliseconds := 10000);
end $$;
do $$ declare f text; begin
  foreach f in array array['bot_secret(text)','bot_set_secret(text,text)','bot_webhook_secret()','bot_save(jsonb,bigint)','bot_merge(jsonb,jsonb,jsonb)','bot_dispatch(text)'] loop
    execute format('revoke all on function public.%s from public, anon, authenticated', f);
    execute format('grant execute on function public.%s to service_role', f);
  end loop;
end $$;
