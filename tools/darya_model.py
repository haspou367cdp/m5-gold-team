"""DaryaGold contract model (pure Python, no I/O): units, costs, P&L, 60-second hold, stop-out proximity.

Every number below came from the owner. The fee (14,000 toman, charged once per trade) was confirmed by the
owner on 2026-11-20, as were the margins (1U 1,000,000 / 0.5U 500,000; stop-out at 80% = 800,000 / 400,000).
The other values (toman per $1, spread, 60-second hold) are not yet verified on the DaryaGold panel.
Prices are in USD per ounce; money is in toman.
"""
from datetime import datetime

SOURCE = "USER_PROVIDED — NOT CURRENTLY VERIFIED"
FEE_SOURCE = "USER_CONFIRMED 2026-11-20 — charged once per trade"
MARGIN_SOURCE = "USER_CONFIRMED 2026-11-20 — initial margin; stop-out at 80% of it"


def _v(value, note=""):
    return {"value": value, "source": SOURCE, "note": note}


UNITS = {
    "1U": {"label_fa": "یک واحد", "margin": {"value": 1_000_000, "source": MARGIN_SOURCE, "note": ""}, "toman_per_usd": _v(80_000),
           "fee": {"value": 14_000, "source": FEE_SOURCE, "note": ""}, "stop_out_loss": {"value": 800_000, "source": MARGIN_SOURCE, "note": "80% of margin"}},
    "0.5U": {"label_fa": "نیم واحد", "margin": {"value": 500_000, "source": MARGIN_SOURCE, "note": ""}, "toman_per_usd": _v(40_000),
             "fee": {"value": 14_000, "source": FEE_SOURCE, "note": ""}, "stop_out_loss": {"value": 400_000, "source": MARGIN_SOURCE, "note": "80% of margin"}},
}
UNIT_ALIASES = {"full_unit": "1U", "half_unit": "0.5U", "1U": "1U", "0.5U": "0.5U"}
STOP_OUT_PCT = _v(80, "of margin")
MIN_HOLD_SECONDS = _v(60)
ORDER_COST_USD = {"MARKET": _v(0.25, "spread paid once per round trip"), "LIMIT": _v(0.0)}
FEE_ONCE = "ONCE"                     # fee charged once per trade
FEE_ENTRY_AND_EXIT = "ENTRY_AND_EXIT"  # fee charged on entry and again on exit
FEE_SCENARIOS = (FEE_ONCE, FEE_ENTRY_AND_EXIT)
DEFAULT_FEE_SCENARIO = FEE_ONCE        # owner-confirmed 2026-11-20; ENTRY_AND_EXIT stays computable only
SIDES = ("BUY", "SELL")


def unit(key):
    k = UNIT_ALIASES.get(key)
    if not k:
        raise ValueError(f"unknown unit {key!r}")
    u = UNITS[k]
    return {"key": k, "label_fa": u["label_fa"], "margin": u["margin"]["value"],
            "toman_per_usd": u["toman_per_usd"]["value"], "fee": u["fee"]["value"],
            "stop_out_loss": u["stop_out_loss"]["value"], "source": SOURCE}


def fee_total(unit_key, scenario=FEE_ONCE):
    if scenario not in FEE_SCENARIOS:
        raise ValueError(f"unknown fee scenario {scenario!r}")
    f = unit(unit_key)["fee"]
    return f * (2 if scenario == FEE_ENTRY_AND_EXIT else 1)


def order_cost_usd(order_type="MARKET", spread_usd=None):
    """Market pays the spread (current if given, never below the model's 0.25); a limit pays nothing."""
    ot = str(order_type).upper()
    if ot not in ORDER_COST_USD:
        raise ValueError(f"unknown order type {order_type!r}")
    base = ORDER_COST_USD[ot]["value"]
    if ot == "MARKET" and spread_usd is not None:
        base = max(base, float(spread_usd))
    return base


def _num(x, name):
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise ValueError(f"{name} is not a number")
    if v != v or v <= 0:
        raise ValueError(f"{name} must be a positive number")
    return v


def gross_pnl_usd(side, entry, exit_price):
    if side not in SIDES:
        raise ValueError(f"side must be BUY or SELL, got {side!r}")
    e, x = _num(entry, "entry"), _num(exit_price, "exit")
    return (x - e) if side == "BUY" else (e - x)


def pnl(side, entry, exit_price, unit_key="1U", order_type="MARKET", fee_scenario=FEE_ONCE, spread_usd=None):
    u = unit(unit_key)
    g_usd = gross_pnl_usd(side, entry, exit_price)
    gross = g_usd * u["toman_per_usd"]
    spread = order_cost_usd(order_type, spread_usd) * u["toman_per_usd"]
    fee = fee_total(unit_key, fee_scenario)
    return {"gross_usd": round(g_usd, 4), "gross_toman": round(gross), "spread_toman": round(spread),
            "fee_toman": fee, "net_toman": round(gross - spread - fee), "unit": u["key"],
            "order_type": str(order_type).upper(), "fee_scenario": fee_scenario}


def trade_economics(side, entry, sl, tp, unit_key="1U", order_type="MARKET", fee_scenario=FEE_ONCE, spread_usd=None):
    """Net loss at SL, net gain at TP and net R:R (reward / risk), both after spread and fees."""
    entry, sl, tp = _num(entry, "entry"), _num(sl, "sl"), _num(tp, "tp")
    if side == "BUY" and not (sl < entry < tp):
        raise ValueError("BUY needs sl < entry < tp")
    if side == "SELL" and not (tp < entry < sl):
        raise ValueError("SELL needs tp < entry < sl")
    at_sl = pnl(side, entry, sl, unit_key, order_type, fee_scenario, spread_usd)
    at_tp = pnl(side, entry, tp, unit_key, order_type, fee_scenario, spread_usd)
    risk, reward = -at_sl["net_toman"], at_tp["net_toman"]
    return {"risk_toman": risk, "reward_toman": reward, "net_rr": round(reward / risk, 3) if risk > 0 else None,
            "fee_scenario": fee_scenario, "unit": at_sl["unit"], "order_type": at_sl["order_type"]}


def worst_case_economics(side, entry, sl, tp, unit_key="1U", order_type="MARKET", spread_usd=None):
    """Both fee scenarios; returns the one with the lower net R:R (the worse), plus both."""
    both = {s: trade_economics(side, entry, sl, tp, unit_key, order_type, s, spread_usd) for s in FEE_SCENARIOS}
    worst = min(both.values(), key=lambda e: (e["net_rr"] if e["net_rr"] is not None else -1e9))
    return dict(worst, scenarios=both)


def limit_counts_as_trade(order_type, filled):
    """A limit order that never filled is not a trade (no P&L, no journal row, no loss count)."""
    return bool(filled) if str(order_type).upper() == "LIMIT" else True


def min_hold_ok(opened_at, closed_at, min_seconds=None):
    """True when the position was held at least the minimum (60 s) before a manual close / TP."""
    m = MIN_HOLD_SECONDS["value"] if min_seconds is None else min_seconds
    if not isinstance(opened_at, datetime) or not isinstance(closed_at, datetime):
        raise ValueError("opened_at and closed_at must be datetimes")
    return (closed_at - opened_at).total_seconds() >= m


def stop_out_check(side, entry, sl, unit_key="1U", order_type="MARKET", spread_usd=None,
                   safety_margin=0.25, warn_ratio=0.5, fee_scenario=DEFAULT_FEE_SCENARIO):
    """Loss at SL (fee scenario, with spread) as a share of the stop-out loss (80% of margin).
    REJECT when the SL loss is inside the safety margin of stop-out (ratio >= 1 - safety_margin),
    WARN from warn_ratio, else OK."""
    u = unit(unit_key)
    entry, sl = _num(entry, "entry"), _num(sl, "sl")
    sl_usd = abs(entry - sl)
    loss = sl_usd * u["toman_per_usd"] + order_cost_usd(order_type, spread_usd) * u["toman_per_usd"] \
        + fee_total(unit_key, fee_scenario)
    ratio = loss / u["stop_out_loss"]
    status = "REJECT" if ratio >= 1 - safety_margin else ("WARN" if ratio >= warn_ratio else "OK")
    return {"status": status, "ratio": round(ratio, 3), "loss_at_sl_toman": round(loss),
            "stop_out_loss_toman": u["stop_out_loss"],
            "stop_out_distance_usd": round(u["stop_out_loss"] / u["toman_per_usd"], 2)}
