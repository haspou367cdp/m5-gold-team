import json, os, sys, urllib.request, uuid
T = os.environ["TG"].strip()
D = os.path.dirname(os.path.abspath(__file__))
chat = open(os.path.join(D, "chat_id.txt")).read().strip()
rd = lambda f: open(os.path.join(D, f), encoding="utf-8").read().strip()
import time
def call(m, d):
    for i in range(4):
        r = urllib.request.Request(f"https://api.telegram.org/bot{T}/{m}", data=json.dumps(d).encode(), headers={"content-type": "application/json"})
        try: return json.load(urllib.request.urlopen(r, timeout=30))
        except urllib.error.HTTPError as e: return json.load(e)
        except Exception as e:
            print(m, "retry after", type(e).__name__, flush=True); time.sleep(3 * (i + 1))
    return {"ok": False, "description": "network"}
def doc(path, caption):
    b = uuid.uuid4().hex; data = open(path, "rb").read()
    parts = [f'--{b}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat}\r\n',
             f'--{b}\r\nContent-Disposition: form-data; name="parse_mode"\r\n\r\nHTML\r\n',
             f'--{b}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n']
    body = "".join(parts).encode() + f'--{b}\r\nContent-Disposition: form-data; name="document"; filename="{os.path.basename(path)}"\r\nContent-Type: text/plain\r\n\r\n'.encode() + data + f"\r\n--{b}--\r\n".encode()
    r = urllib.request.Request(f"https://api.telegram.org/bot{T}/sendDocument", data=body, headers={"content-type": f"multipart/form-data; boundary={b}"})
    try: return json.load(urllib.request.urlopen(r, timeout=60))
    except urllib.error.HTTPError as e: return json.load(e)
me = call("getMe", {}); bot = me.get("result", {}).get("username", "")
print("bot:", bot)
out = []
SKIP_DOC = os.path.exists(os.path.join(D, "doc_sent.txt"))   # run 2 sent the document before a network reset
if not SKIP_DOC:
    r = doc(os.path.join(D, "..", "xauscalper_zones.pine"), rd("caption.html")); out.append(("document", r))
for f in ("guide.html", "intro1.html", "intro2.html"):
    t = rd(f).replace("{BOT}", bot)
    r = call("sendMessage", {"chat_id": chat, "text": t, "parse_mode": "HTML", "disable_web_page_preview": True}); out.append((f, r))
    print(f, "ok" if r.get("ok") else "FAIL", r.get("result", {}).get("message_id") if r.get("ok") else r.get("description"), flush=True)
    time.sleep(1.5)
bad = 0
for name, r in out:
    print(name, "ok" if r.get("ok") else "FAIL", r.get("result", {}).get("message_id") if r.get("ok") else r.get("description"))
    bad += 0 if r.get("ok") else 1
sys.exit(1 if bad else 0)
