"""Guards for the 2026-11-20 SELL limit bug and the owner-approved risk rules."""
import os, sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_level_view():
    """Load this branch's level_view, even if another suite already imported the main checkout."""
    import importlib.util
    path = os.path.join(ROOT, "tools", "level_view.py")
    spec = importlib.util.spec_from_file_location("level_view_redesign", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

sys.path.insert(0, os.path.join(ROOT, "bot"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import signal_guards as SG
import darya_model as DM
import broker_daryagold as DG

TEH = ZoneInfo("Asia/Tehran")
T = lambda *a: datetime(*a, tzinfo=TEH)
CFG = DG.load_config()

# The card the owner saw around 18:30 Tehran on 2026-11-20.
ENTRY_DG, SL_DG, TP_DG = 3595.4, 3597.2, 3566.4
# bid-space equivalents at a +0.3 offset
ENTRY, SL, TP = 3595.1, 3596.9, 3566.1
PRICE = 3576.3   # ~3576.6 DaryaGold
ATR9 = 9.0
INV = 3590.37    # M15 neutralisation from that session's brief


def test_limit_risk_on_card_prices_is_158k_not_185k():
    """1.8×80,000 + 14,000 = 158,000. The 185k figure added a $0.25–0.34 spread on a LIMIT
    and used unrounded bid distances (about $1.89) instead of the 1-decimal card prices."""
    econ = SG.limit_economics("SELL", ENTRY_DG, SL_DG, TP_DG, "1U")
    assert abs((SL_DG - ENTRY_DG) - 1.8) < 1e-9
    assert econ["risk_toman"] == 1.8 * 80_000 + 14_000 == 158_000
    # What the old MARKET sizing would have printed with a 0.25 spread and a 1.8875 raw stop:
    old = 1.8875 * 80_000 + 14_000 + 0.25 * 80_000
    assert int(round(old)) == 185_000


def test_displayed_prices_match_the_card():
    e, sl, tp = SG.display_prices(ENTRY, SL, TP, CFG, DG.to_broker)
    assert (e, sl, tp) == (ENTRY_DG, SL_DG, TP_DG)


def test_min_stop_uses_half_atr_and_never_shrinks():
    # 0.5 × $9 ATR = $4.5, which beats $1 and structure+$0.5 when entry sits on the level.
    floor = SG.min_stop_usd(ENTRY, ENTRY, ATR9)
    assert abs(floor - 4.5) < 1e-9
    sl = SG.sl_price("SELL", ENTRY, ENTRY, ATR9)
    assert abs(sl - (ENTRY + 4.5)) < 1e-9
    # The $1.8 stop on the card is tighter than the floor and must be rejected, not shrunk.
    g = SG.evaluate("SELL", ENTRY, SL, TP, price=PRICE, atr_m5=ATR9, remaining_adr_usd=20,
                    structure=ENTRY, invalidation=INV, unit="1U", net_rr=12.3)
    assert not g["ok"]
    assert any("تنگ‌تر" in r or "حد ضرر" in r for r in g["reasons_fa"])


def test_pending_limit_too_far_and_beyond_invalidation():
    why = SG.pending_limit_reasons("SELL", ENTRY, PRICE, ATR9, invalidation=INV)
    assert any("فاصله" in w for w in why)
    assert any("ابطال" in w for w in why)
    # A limit $4 below price and 0.4×ATR, under the invalidation, is allowed.
    ok = SG.pending_limit_reasons("SELL", PRICE + 4.0, PRICE, ATR9, invalidation=PRICE + 10)
    assert ok == []


def test_rr_above_8_rejected_above_5_warns():
    st, msg = SG.rr_status(12.3)
    assert st == "reject" and "۸" in msg
    st, msg = SG.rr_status(6.2)
    assert st == "warn" and "۵" in msg
    st, msg = SG.rr_status(3.0)
    assert st == "ok" and msg is None


def test_tp_capped_by_three_atr_and_remaining_adr():
    why = SG.tp_reasons(ENTRY, TP, ATR9, remaining_adr=10, mapped=True)
    # 29$ target vs min(10, 27) = 10 → rejected
    assert why and any("حد سود" in w for w in why)
    why = SG.tp_reasons(ENTRY, ENTRY - 8, ATR9, remaining_adr=20, mapped=True)
    assert why == []


def test_stop_out_buffer_vetoes_wide_atr():
    # sl $1.8 + ATR $9 = 10.8, which is above 50% of the ~$10 stop-out.
    ok, used, cap, so = SG.stop_out_buffer_ok(1.8, ATR9, "1U")
    assert so == 10.0 and cap == 5.0 and not ok and used == 10.8
    # A tight-ATR, tight-stop case can pass: sl $1.5 + ATR $2 = 3.5 <= 5.
    ok, *_ = SG.stop_out_buffer_ok(1.5, 2.0, "1U")
    assert ok
    # Fee is 14,000 once for both sizes (0.5U stop-out is also ~$10).
    assert DM.unit("0.5U")["fee"] == DM.unit("1U")["fee"] == 14_000
    assert DM.unit("0.5U")["stop_out_loss"] / DM.unit("0.5U")["toman_per_usd"] == 10.0


def test_the_user_signal_is_rejected_for_every_broken_rule():
    g = SG.evaluate("SELL", ENTRY, SL, TP, price=PRICE, atr_m5=ATR9, remaining_adr_usd=15,
                    structure=ENTRY, invalidation=INV, unit="1U", net_rr=12.3)
    assert not g["ok"]
    blob = " ".join(g["reasons_fa"])
    assert "حد ضرر" in blob and "فاصله" in blob and "ابطال" in blob
    assert any("۸" in r or "نسبت" in r for r in g["reasons_fa"])


def test_expiry_max_30_min_cut_before_news_and_friday_cancel():
    now = T(2026, 11, 20, 18, 30)
    exp = SG.signal_expiry(now, {"next_start": "2026-11-20 20:30", "soon_action": "block"},
                           session_close=T(2026, 11, 21, 0, 30))
    assert exp == now + timedelta(minutes=30)
    # Next A/B window inside 30 min clips expiry.
    exp = SG.signal_expiry(now, {"next_start": "2026-11-20 18,50".replace(",", ":"), "soon_action": "block"},
                           session_close=T(2026, 11, 21, 0, 30))
    assert exp == T(2026, 11, 20, 18, 50)
    # A time already past is expired; it must not be re-armed.
    assert SG.is_expired(T(2026, 11, 20, 16, 0), T(2026, 11, 20, 18, 30))
    assert not SG.is_expired(T(2026, 11, 20, 19, 0), T(2026, 11, 20, 18, 30))


def test_friday_entry_cutoff_is_2330():
    se = DG.session_entry_block(T(2026, 11, 20, 23, 30), CFG)
    assert se["blocked"] and se["friday_window"] and se["block_start_tehran"].endswith("23:30")
    assert not DG.session_entry_block(T(2026, 11, 20, 23, 29), CFG)["blocked"]
    # A Friday 23:10 signal expires at the 23:30 pending-cancel, not 23:40.
    import bot as B
    B.CFG = CFG
    exp = B.signal_expiry({"news_window": {}}, CFG, T(2026, 11, 20, 23, 10))
    assert exp == T(2026, 11, 20, 23, 30)


def test_format_block_drops_importance_and_touch_count():
    LV = load_level_view()
    snap = {
        "price_dg": 3576.6, "as_of_tehran": "2026-11-20 18:30:00", "source": "Dukascopy freeserv XAU/USD",
        "regime": {"code": "volatility_expansion", "fa": "گسترش نوسان"},
        "atr_m5": 9.0, "zone_half": 2.25,
        "trend": {"H4": {"trend": "نزولی"}, "H1": {"trend": "نزولی"},
                  "M15": {"trend": "خنثی"}, "M5": {"trend": "خنثی"}, "overall": "نزولی",
                  "verdict": "جمع‌بندی: نزولی"},
        "short": {"above": [
            {"price_dg": 3595.3, "distance": 18.7, "distance_atr": 2.1,
             "kinds": ["London high", "H1 swing high"], "label_fa": "سقف لندن + سوئینگ H1",
             "tag": "خیلی مهم", "touches_m15_3d": 2},
        ], "below": [
            {"price_dg": 3572.9, "distance": -3.7, "distance_atr": 0.4,
             "kinds": ["NY OR low"], "label_fa": "OR نیویورک",
             "tag": "مهم", "touches_m15_3d": 8},
        ]},
        "news_line": "خبر: پنجره‌ی جاری تا 18:45",
    }
    block = LV.format_block(snap)
    assert "خیلی مهم" not in block and "مهم" not in block
    assert "تماس M15" not in block and "قوی" not in block and "زیان" not in block
    # plain wording for beginners: dollar distance and plain origin, no ATR / OR / regime / zone jargon
    assert "3.7 دلار پایین‌تر" in block and "کف شروع عصر" in block
    assert "دریاگلد" in block and "18:30 به وقت تهران" in block
    assert not any(x in block for x in ("ATR", "OR ", "رژیم", "پهنه", "M5", "H1", "H4"))
    assert "ورود" not in block and "حد ضرر" not in block and "هدف" not in block


def test_merge_overlapping_zones_keeps_tags():
    LV = load_level_view()
    a = {"price": 3600.0, "price_dg": 3600.3, "zone_dg": [3599.0, 3601.6],
         "kinds": ["Round $100"], "label_fa": "رُند 3600", "side": "resistance"}
    b = {"price": 3600.8, "price_dg": 3601.1, "zone_dg": [3599.8, 3602.4],
         "kinds": ["London high"], "label_fa": "سقف لندن", "side": "resistance"}
    out = LV.merge_zones([a, b], price_bid=3576.0)
    assert len(out) == 1
    assert set(out[0]["kinds"]) == {"Round $100", "London high"}
    assert "عدد رُند 3600" in out[0]["label_fa"] and "سقف ظهر امروز" in out[0]["label_fa"]


def test_zone_half_floor_is_one_dollar():
    LV = load_level_view()
    assert LV.zone_half(2.0) == 1.0
    assert LV.zone_half(8.0) == 2.0
