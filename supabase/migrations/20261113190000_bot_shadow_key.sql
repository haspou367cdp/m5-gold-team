-- Shadow log: the GitHub run may also merge its "shadow" key (silent log of gate-blocked setups).
create or replace function public.bot_merge(p_patch jsonb, p_done jsonb, p_news jsonb) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare allowed text[] := array['signals_sent','presession_sent','last_run_tehran','last_verdict','news_fetched_at','shadow'];
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
revoke all on function public.bot_merge(jsonb,jsonb,jsonb) from public, anon, authenticated;
grant execute on function public.bot_merge(jsonb,jsonb,jsonb) to service_role;
