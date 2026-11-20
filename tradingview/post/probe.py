# Read-only intent: editMessageCaption with the IDENTICAL caption returns "message is not modified" only for our document.
import json, os, urllib.request
T = os.environ["TG"].strip(); D = os.path.dirname(os.path.abspath(__file__))
chat = open(os.path.join(D, "chat_id.txt")).read().strip()
cap = open(os.path.join(D, "caption.html"), encoding="utf-8").read().strip()
for mid in (2962, 2961):
    r = urllib.request.Request(f"https://api.telegram.org/bot{T}/editMessageCaption", data=json.dumps({"chat_id": chat, "message_id": mid, "caption": cap, "parse_mode": "HTML"}).encode(), headers={"content-type": "application/json"})
    try: x = json.load(urllib.request.urlopen(r, timeout=30))
    except urllib.error.HTTPError as e: x = json.load(e)
    print(mid, x.get("ok"), x.get("description"))
