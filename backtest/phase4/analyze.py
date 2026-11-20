"""Summarise the Phase 4 replay (backtest/phase4/out/*.json) into REPORT.md + results.json. HISTORICAL SIMULATION."""
import glob, json, os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out")
IS_END = "2023-12-31"
SES = [("07:00-11:15", "07:00", "11:15"), ("11:15-16:15", "11:15", "16:15"), ("16:15-00:30", "16:15", "24:00")]


def session_of(t):
    hm = t[11:16]
    if hm < "07:00":
        return "16:15-00:30"
    for name, a, b in SES:
        if a <= hm < b:
            return name
    return "16:15-00:30"


def load():
    days, rows, errs = [], [], []
    for f in sorted(glob.glob(os.path.join(OUT, "*.json"))):
        for d in json.load(open(f)):
            days.append({"day": d["day"], "evals": d["evals"], "stop_hit": d["stop_hit"]})
            for r in d["rows"]:
                (errs if "error" in r else rows).append(r)
    D = pd.DataFrame(days)
    R = pd.DataFrame(rows)
    D["period"] = np.where(D.day <= IS_END, "IS", "OOS")
    if len(R):
        R["period"] = np.where(R.day <= IS_END, "IS", "OOS")
        R["session"] = R.t_teh.map(session_of)
    return D, R, errs


def maxdd(x):
    if not len(x):
        return 0.0
    c = np.cumsum(x)
    return float(np.max(np.maximum.accumulate(np.concatenate([[0], c]))[1:] - c))


def stats(sig, days_stop=None):
    t = sig[sig.filled == True].sort_values(["day", "t_teh"]) if len(sig) else sig
    n = len(t)
    o = {"signals": int(len(sig)), "filled": int(n), "expired": int(len(sig) - n)}
    if n:
        o.update(win_rate=round(100 * float((t.net > 0).mean()), 1), avg_R=round(float(t.R.mean()), 3), total_R=round(float(t.R.sum()), 1),
                 net_toman=int(t.net.sum()), avg_toman=int(round(t.net.mean())), max_dd_toman=int(maxdd(t.net.to_numpy())),
                 max_dd_R=round(maxdd(t.R.to_numpy()), 1), tp=int((t.exit_type == "tp").sum()), sl=int((t.exit_type == "sl").sum()),
                 close=int((t.exit_type == "close").sum()), stop_out=int((t.exit_type == "stop_out").sum()),
                 tp_deferred_60s=int((t.tp_deferred > 0).sum()), avg_R_spread050=round(float(t.R_s50.mean()), 3),
                 net_toman_spread050=int(t.net_s50.sum()), mfe_R_med=round(float(t.mfe_R.median()), 2),
                 mae_R_med=round(float(t.mae_R.median()), 2), hold_min_med=round(float(t.hold_min.median()), 1),
                 t_stat=round(float(t.R.mean() / (t.R.std(ddof=1) / np.sqrt(n))), 2) if n > 2 and t.R.std(ddof=1) > 0 else None,
                 small_sample=n < 30)
    return o


def md_table(T):
    head = "| " + " | ".join(T.columns) + " |"
    sep = "|" + "---|" * len(T.columns)
    rows = ["| " + " | ".join("" if (v is None or (isinstance(v, float) and np.isnan(v))) else str(v) for v in r) + " |" for r in T.itertuples(index=False)]
    return "\n".join([head, sep] + rows)


def main():
    D, R, errs = load()
    res = {"label": "HISTORICAL SIMULATION — not live results, no edge claimed", "days": {}, "tables": [], "errors": len(errs)}
    for p in ("IS", "OOS"):
        dd = D[D.period == p]
        res["days"][p] = {"sessions": int(len(dd)), "evaluations": int(dd.evals.sum()), "daily_stop_hits": int(dd.stop_hit.sum()),
                          "first": dd.day.min(), "last": dd.day.max()}
    for p in ("IS", "OOS"):
        for eng in ("ALL", "continuation", "sweep_reversion"):
            for ses in ("ALL",) + tuple(s[0] for s in SES):
                sub = R[(R.period == p)] if len(R) else R
                if len(sub) and eng != "ALL":
                    sub = sub[sub.engine == eng]
                if len(sub) and ses != "ALL":
                    sub = sub[sub.session == ses]
                res["tables"].append({"period": p, "engine": eng, "session": ses, **stats(sub)})
    json.dump(res, open(os.path.join(HERE, "results.json"), "w"), indent=1, default=str)
    cols = ["period", "engine", "session", "signals", "filled", "win_rate", "avg_R", "total_R", "net_toman", "max_dd_toman", "max_dd_R",
            "tp", "sl", "close", "stop_out", "tp_deferred_60s", "avg_R_spread050", "mfe_R_med", "mae_R_med", "t_stat"]
    T = pd.DataFrame(res["tables"])
    for c in cols:
        if c not in T:
            T[c] = None
    L = ["# Phase 4 replay — HISTORICAL SIMULATION (not live results; no edge claimed)", "",
         "Rules frozen in PREREG.md before running (hashes in HASHES.txt). Live parameters were NOT changed from these results.",
         "Live engines as of c80b513, DaryaGold cost model (fee 14,000 once, $0.25 spread, 1U 80,000/$ · 0.5U 40,000/$), 60 s rule,",
         "Tehran 07:00–00:30 incl. 07:00–11:15, fixed equity 2,954,400 toman. News gate inactive (no historical calendar).", "",
         "| period | sessions | evaluations | daily-stop hits | range |", "|---|---|---|---|---|"]
    for p, v in res["days"].items():
        L.append(f"| {p} | {v['sessions']} | {v['evaluations']} | {v['daily_stop_hits']} | {v['first']} … {v['last']} |")
    L += ["", f"Engine errors during replay: {len(errs)}", "", md_table(T[cols])]
    open(os.path.join(HERE, "REPORT.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L[:12]))
    print(T[T.session == "ALL"][cols].to_string(index=False))


if __name__ == "__main__":
    main()
