#!/usr/bin/env python3
"""sync_trades.py - append manual trades recorded with Telegram /trade (bot_state.trades in Supabase) to the box's
journal.csv (git-ignored, never written by the GitHub runner). Idempotent: rows are keyed by signal_id.

usage: python3 tools/sync_trades.py STATE_JSON [--journal journal.csv] [--dry-run]
STATE_JSON: the bot_state.state jsonb (e.g. exported with:  select state from public.bot_state where id = 1).
A trade later removed with /undo is no longer in state.trades; rows already appended are left alone (append-only)."""
import argparse, csv, json, os, sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def session(hm):
    return "Asia" if hm < "10:30" else "London" if hm < "16:30" else "NY"

def row(t, logged):
    d = 1 if t["side"] == "buy" else -1
    rate = 80000 if float(t["units"]) == 1 else 40000
    move = round((float(t["exit"]) - float(t["entry"])) * d, 2)
    return {"signal_id": t["id"], "logged_at_tehran": logged, "signal_time_tehran": f"{t['date']} {t['at']}",
            "session": session(t["at"]), "setup_type": "manual (not a bot signal)", "direction": t["side"],
            "entry": t["entry"], "source_bot": "manual /trade", "risk_decision": "n/a (manual)",
            "risk_reason": "owner trade, not a bot signal", "status": "closed", "exit_price": t["exit"],
            "outcome": "win" if t["net"] >= 0 else "loss",
            "notes": f"recorded with Telegram /trade at {t['date']} {t['at']} Tehran (time of the command, not the ticket); "
                     f"gross {t['gross']} before {t['fee']} fee",
            "broker": "DaryaGold", "unit_size": "full" if rate == 80000 else "half", "toman_per_usd": rate,
            "fee_toman": t["fee"], "price_offset_usd": 0.3, "equity_start_toman": round(t["equity_before"]),
            "pnl_usd": move, "pnl_toman_gross": t["gross"], "pnl_toman_net": t["net"],
            "equity_after_toman": round(t["equity_after"])}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("state")
    ap.add_argument("--journal", default=f"{ROOT}/journal.csv")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    st = json.load(open(a.state))
    st = st.get("state", st)
    with open(a.journal, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        cols, have = r.fieldnames, {x["signal_id"] for x in r}
    logged = datetime.now(ZoneInfo("Asia/Tehran")).strftime("%Y-%m-%d %H:%M")
    new = [row(t, logged) for t in st.get("trades") or [] if t.get("id") and t["id"] not in have]
    for n in new:
        print("append", n["signal_id"], n["direction"], n["entry"], "->", n["exit_price"], "net", n["pnl_toman_net"])
    if new and not a.dry_run:
        with open(a.journal, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            for n in new:
                w.writerow({k: n.get(k, "") for k in cols})
    print(f"{len(new)} new trade(s)" + (" (dry run)" if a.dry_run else ""))

if __name__ == "__main__":
    sys.exit(main())
