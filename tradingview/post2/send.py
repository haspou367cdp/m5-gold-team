import json, os, sys, time, urllib.request, urllib.error, uuid
T = os.environ["TG"].strip(); D = os.path.dirname(os.path.abspath(__file__))
chat = open(os.path.join(D, "chat_id.txt")).read().strip()
rd = lambda f: open(os.path.join(D, f), encoding="utf-8").read().strip()
def post(req):
    for i in range(4):
        try: return json.load(urllib.request.urlopen(req(), timeout=60))
        except urllib.error.HTTPError as e: return json.load(e)
        except Exception as e:
            print("retry after", type(e).__name__, flush=True); time.sleep(3 * (i + 1))
    return {"ok": False, "description": "network"}
def doc(path, caption):
    b = uuid.uuid4().hex; data = open(path, "rb").read()
    body = "".join(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n' for k, v in (("chat_id", chat), ("parse_mode", "HTML"), ("caption", caption))).encode()
    body += f'--{b}\r\nContent-Disposition: form-data; name="document"; filename="{os.path.basename(path)}"\r\nContent-Type: text/plain\r\n\r\n'.encode() + data + f"\r\n--{b}--\r\n".encode()
    return post(lambda: urllib.request.Request(f"https://api.telegram.org/bot{T}/sendDocument", data=body, headers={"content-type": f"multipart/form-data; boundary={b}"}))
def msg(text):
    return post(lambda: urllib.request.Request(f"https://api.telegram.org/bot{T}/sendMessage", data=json.dumps({"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}).encode(), headers={"content-type": "application/json"}))
bad = 0
for name, fn in (("doc_fa", lambda: doc(os.path.join(D, "..", "xauscalper_zones.pine"), rd("cap_fa.html"))),
                 ("doc_en", lambda: doc(os.path.join(D, "..", "xauscalper_zones_en.pine"), rd("cap_en.html"))),
                 ("message", lambda: msg(rd("msg.html")))):
    r = fn()
    print(name, "ok" if r.get("ok") else "FAIL", r.get("result", {}).get("message_id") if r.get("ok") else r.get("description"), flush=True)
    if not r.get("ok"): bad += 1; break
    time.sleep(1.5)
sys.exit(1 if bad else 0)
