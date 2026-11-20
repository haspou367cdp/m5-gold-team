# One-off, read-only Telegram health probe: getMe and getWebhookInfo (no token, no webhook secret printed). Sends nothing.
import json, os, time, urllib.request
T = os.environ["TG"].strip()
def call(m, d, tries=3):
    for i in range(tries):
        t0 = time.time()
        try:
            r = urllib.request.Request(f"https://api.telegram.org/bot{T}/{m}", data=json.dumps(d).encode(), headers={"content-type": "application/json"})
            out = json.load(urllib.request.urlopen(r, timeout=15))
            print(m, "ok in", round(time.time() - t0, 1), "s", flush=True)
            return out
        except Exception as e:
            print(m, "attempt", i + 1, type(e).__name__, "after", round(time.time() - t0, 1), "s", flush=True); time.sleep(3)
    return {}
me = call("getMe", {}, 1).get("result", {})
if not me: raise SystemExit("getMe: no answer")
print("BOT first_name:", me.get("first_name"), "| username:", me.get("username"))
w = call("getWebhookInfo", {}, 1).get("result", {})
u = w.get("url") or ""
print("WEBHOOK host:", u.split("/")[2] if u.count("/") > 2 else u, "| path_ok:", u.endswith("/tg-bot/tg"), "| pending:", w.get("pending_update_count"),
      "| last_error:", w.get("last_error_message"), "| last_error_date:", w.get("last_error_date"))
for k, d in (("getMyName", {}), ("getMyName", {"language_code": "fa"}), ("getMyDescription", {"language_code": "fa"}), ("getMyShortDescription", {"language_code": "fa"}),
             ("getMyCommands", {"scope": {"type": "chat", "chat_id": 45639251}}), ("getMyCommands", {"scope": {"type": "chat", "chat_id": -1001958445009}})):
    print(k, d.get("language_code", ""), json.dumps(call(k, d, 1).get("result"), ensure_ascii=False)[:900])
ch = call("getChat", {"chat_id": -1001958445009}, 1).get("result", {})
print("GROUP title:", ch.get("title"))
