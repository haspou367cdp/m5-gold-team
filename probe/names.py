# One-off, read-only: prints the bot's display name/username and the group's title. The token is never printed.
import json, os, urllib.request
T = os.environ["TG"].strip()
import time
def call(m, d):
    for i in range(5):
        try:
            r = urllib.request.Request(f"https://api.telegram.org/bot{T}/{m}", data=json.dumps(d).encode(), headers={"content-type": "application/json"})
            return json.load(urllib.request.urlopen(r, timeout=30))
        except Exception as e:
            print(m, "retry", type(e).__name__, flush=True); time.sleep(4 * (i + 1))
    return {}
me = call("getMe", {}).get("result", {})
print("BOT first_name:", me.get("first_name"), "| username:", me.get("username"), "| id:", me.get("id"))
ch = call("getChat", {"chat_id": -1001958445009}).get("result", {})
print("GROUP title:", ch.get("title"), "| username:", ch.get("username"), "| type:", ch.get("type"))
for k in ("getMyName", "getMyDescription", "getMyShortDescription"):
    try: print(k, json.dumps(call(k, {}).get("result"), ensure_ascii=False))
    except Exception as e: print(k, "n/a", type(e).__name__)
