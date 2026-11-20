# One-off: posts the Xauscalper Map indicator (fa, en) and the group guide to the BAROBAX group (owner t238u).
# The token comes from GitHub secrets and is never printed. Stops at the first failure so nothing is sent twice on a re-run.
import json, os, sys, time, urllib.request, urllib.error, uuid
T = os.environ["TG"].strip()
D = os.path.dirname(os.path.abspath(__file__))
chat = open(os.path.join(D, "chat_id.txt")).read().strip()
rd = lambda f: open(os.path.join(D, f), encoding="utf-8").read().strip()
def call(m, d):
    r = urllib.request.Request(f"https://api.telegram.org/bot{T}/{m}", data=json.dumps(d).encode(), headers={"content-type": "application/json"})
    try: return json.load(urllib.request.urlopen(r, timeout=30))
    except urllib.error.HTTPError as e: return json.load(e)
    except Exception as e: return {"ok": False, "description": type(e).__name__}
def doc(path, caption):
    b = uuid.uuid4().hex; data = open(path, "rb").read()
    parts = [f'--{b}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat}\r\n',
             f'--{b}\r\nContent-Disposition: form-data; name="parse_mode"\r\n\r\nHTML\r\n',
             f'--{b}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n']
    body = "".join(parts).encode() + f'--{b}\r\nContent-Disposition: form-data; name="document"; filename="{os.path.basename(path)}"\r\nContent-Type: text/plain\r\n\r\n'.encode() + data + f"\r\n--{b}--\r\n".encode()
    r = urllib.request.Request(f"https://api.telegram.org/bot{T}/sendDocument", data=body, headers={"content-type": f"multipart/form-data; boundary={b}"})
    try: return json.load(urllib.request.urlopen(r, timeout=60))
    except urllib.error.HTTPError as e: return json.load(e)
    except Exception as e: return {"ok": False, "description": type(e).__name__}
steps = [("doc_fa", lambda: doc(os.path.join(D, "xauscalper_map.pine"), rd("cap_fa.html"))),
         ("doc_en", lambda: doc(os.path.join(D, "xauscalper_map_en.pine"), rd("cap_en.html"))),
         ("guide1", lambda: call("sendMessage", {"chat_id": chat, "text": rd("guide1.html"), "parse_mode": "HTML", "disable_web_page_preview": True})),
         ("guide2", lambda: call("sendMessage", {"chat_id": chat, "text": rd("guide2.html"), "parse_mode": "HTML", "disable_web_page_preview": True}))]
for name, fn in steps:
    r = fn()
    print(name, "ok" if r.get("ok") else "FAIL", r.get("result", {}).get("message_id") if r.get("ok") else r.get("description"), flush=True)
    if not r.get("ok"):
        sys.exit(1)
    time.sleep(1.5)
