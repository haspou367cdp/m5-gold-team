"""Run the LIVE decision pipeline (tools/levels, bias, regime, brief broker gates, risk_gate) at a past instant.

Nothing in tools/ is modified: module-level data loaders are pointed at point-in-time slices for one call.
Known gaps vs live (fixed in PREREG.md): no historical news calendar (news gate inactive), no M5-News bias,
data quality always 'ok' (the replay uses the archive, not a live fetch).
"""
import sys
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, "/workspace/m5-gold-team/tools")
import pandas as pd
import levels as LV, bias as BI, regime as REG, brief as BR, risk_gate as RG, broker_daryagold as DG, m5lib, news_windows as NW

TEH = ZoneInfo("Asia/Tehran")   # historical Iranian DST (UTC+4:30 summers until 2022) handled by tzdata
EMPTY_NEWS = {"windows": [], "news_bias": None}


@contextmanager
def point_in_time(M, t_utc):
    """Point every data loader used by the live pipeline at what was available at t_utc."""
    cache = {}

    def lb(tf):
        if tf not in cache:
            cache[tf] = M.bars_at(tf, t_utc).copy()
        return cache[tf]

    m1 = lb("1m")
    last = m1.index[-1]
    meta = {"ok": True, "stale": False, "market_open": True, "source": "dukascopy-archive",
            "as_of_tehran": last.tz_convert(TEH).strftime("%Y-%m-%d %H:%M"), "last_ask": float(m1.c_a.iloc[-1])}
    store = {}

    def lj(path, default=None):
        if str(path).endswith("meta.json"):
            return dict(meta)
        if str(path).endswith("levels.json"):
            return store.get("lv", default)
        return default

    saved = {}
    patches = [(LV, "load_bars", lb), (BI, "load_bars", lb), (REG, "load_bars", lb), (m5lib, "load_bars", lb),
               (LV, "load_json", lj), (BI, "load_json", lj), (NW, "load", lambda *a, **k: dict(EMPTY_NEWS)),
               (DG, "daily_loss_veto", lambda cfg: (False, "", {"losses": 0}))]
    for mod, name, fn in patches:
        saved[(mod, name)] = getattr(mod, name)
        setattr(mod, name, fn)
    try:
        yield store, meta
    finally:
        for (mod, name), fn in saved.items():
            setattr(mod, name, fn)


def evaluate(M, t_utc, cfg):
    """One live-equivalent evaluation. Returns a compact dict; plan prices are Dukascopy BID (DaryaGold = +offset)."""
    t_teh = pd.Timestamp(t_utc).tz_convert(TEH).to_pydatetime()
    with point_in_time(M, t_utc) as (store, meta):
        lv = LV.compute()
        store["lv"] = lv
        b = BI.compute(t_teh)
        regime = REG.classify(lv, win=b.get("news_window"), spread=b.get("spread"), h4=b.get("h4"), h1=b.get("h1"))
        q = {"ok": True, "fa": "ok", "age_minutes": 0}
        decision = REG.decide(lv, b, regime, quality=q)
        session = DG.session_entry_block(t_teh, cfg)
        dec, plan, sizing, _ = BR._apply_broker_gates(decision, lv, b, cfg, session)
    out = {"t": t_teh.strftime("%Y-%m-%d %H:%M"), "decision": dec.get("decision"), "engine": decision.get("engine"),
           "regime": (regime or {}).get("code"), "allowed_engine": (regime or {}).get("allowed_engine"),
           "spread": (b.get("spread") or {}).get("current"), "bid": lv.get("price_bid")}
    if dec.get("decision") not in ("BUY", "SELL") or not plan or not sizing or not sizing.get("ok") or plan.get("tp") is None:
        out["status"] = "NO_TRADE"
        out["vetoed_after_engine"] = bool(decision.get("decision") in ("BUY", "SELL"))
        return out
    gate = RG.evaluate(t_teh, plan["side"], plan["entry"], plan["sl"], plan["tp"], unit=sizing["size"]["key"],
                       order_type="MARKET", spread_usd=out["spread"], data_ok=True, data_age_min=0, session=session,
                       news_window={}, news_ok=True, cfg=cfg, min_net_rr=float(cfg.get("min_net_rr", 1.5)))
    out.update(status=gate["status"], side=plan["side"], entry=float(plan["entry"]), sl=float(plan["sl"]), tp=float(plan["tp"]),
               unit=sizing["size"]["key"], net_rr=gate["metrics"].get("net_rr"), close_tehran=session.get("close_tehran"))
    return out
