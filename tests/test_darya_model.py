from datetime import datetime, timedelta
import pytest
import darya_model as DM


def test_units_and_sources():
    one, half = DM.unit("1U"), DM.unit("0.5U")
    assert (one["margin"], one["toman_per_usd"], one["fee"], one["stop_out_loss"]) == (1_000_000, 80_000, 14_000, 800_000)
    assert (half["margin"], half["toman_per_usd"], half["fee"], half["stop_out_loss"]) == (500_000, 40_000, 14_000, 400_000)
    assert DM.unit("full_unit")["key"] == "1U" and DM.unit("half_unit")["key"] == "0.5U"
    for u in DM.UNITS.values():
        assert u["toman_per_usd"]["source"] == "USER_PROVIDED — NOT CURRENTLY VERIFIED"
        for k in ("margin", "stop_out_loss"):
            assert u[k]["source"].startswith("USER_CONFIRMED 2026-11-20")
        assert u["fee"]["source"].startswith("USER_CONFIRMED 2026-11-20")
    assert DM.DEFAULT_FEE_SCENARIO == DM.FEE_ONCE
    assert DM.ORDER_COST_USD["MARKET"]["source"] == DM.SOURCE and DM.MIN_HOLD_SECONDS["value"] == 60
    with pytest.raises(ValueError):
        DM.unit("2U")


def test_fee_scenarios():
    assert DM.fee_total("1U", DM.FEE_ONCE) == 14_000
    assert DM.fee_total("1U", DM.FEE_ENTRY_AND_EXIT) == 28_000
    assert DM.fee_total("0.5U", DM.FEE_ENTRY_AND_EXIT) == 28_000
    with pytest.raises(ValueError):
        DM.fee_total("1U", "TWICE")


def test_order_costs():
    assert DM.order_cost_usd("MARKET") == 0.25 and DM.order_cost_usd("LIMIT") == 0.0
    assert DM.order_cost_usd("MARKET", 0.6) == 0.6 and DM.order_cost_usd("MARKET", 0.1) == 0.25
    assert DM.order_cost_usd("LIMIT", 0.6) == 0.0
    assert DM.limit_counts_as_trade("LIMIT", filled=False) is False
    assert DM.limit_counts_as_trade("LIMIT", filled=True) is True
    assert DM.limit_counts_as_trade("MARKET", filled=False) is True


def test_buy_sell_pnl():
    b = DM.pnl("BUY", 3550.0, 3553.0, "1U", "MARKET", DM.FEE_ONCE)
    assert b["gross_toman"] == 240_000 and b["spread_toman"] == 20_000 and b["net_toman"] == 240_000 - 20_000 - 14_000
    s = DM.pnl("SELL", 3550.0, 3553.0, "0.5U", "LIMIT", DM.FEE_ENTRY_AND_EXIT)
    assert s["gross_toman"] == -120_000 and s["spread_toman"] == 0 and s["net_toman"] == -148_000
    assert DM.gross_pnl_usd("SELL", 3550, 3545) == 5
    with pytest.raises(ValueError):
        DM.pnl("HOLD", 1, 2)
    with pytest.raises(ValueError):
        DM.pnl("BUY", None, 2)


def test_net_rr_and_worst_case():
    e = DM.trade_economics("SELL", 3880.0, 3881.6, 3876.0, "1U", "MARKET", DM.FEE_ONCE)
    assert e["risk_toman"] == 128_000 + 20_000 + 14_000 and e["reward_toman"] == 320_000 - 20_000 - 14_000
    w = DM.worst_case_economics("SELL", 3880.0, 3881.6, 3876.0, "1U", "MARKET")
    assert w["fee_scenario"] == DM.FEE_ENTRY_AND_EXIT
    assert w["net_rr"] == round(272_000 / 176_000, 3) < w["scenarios"][DM.FEE_ONCE]["net_rr"]
    with pytest.raises(ValueError):
        DM.trade_economics("BUY", 3880.0, 3881.0, 3885.0)   # SL above entry on a BUY


def test_min_hold():
    t = datetime(2026, 11, 20, 12, 0, 0)
    assert DM.min_hold_ok(t, t + timedelta(seconds=60)) is True
    assert DM.min_hold_ok(t, t + timedelta(seconds=59)) is False
    with pytest.raises(ValueError):
        DM.min_hold_ok("12:00", t)


def test_stop_out_proximity():
    ok = DM.stop_out_check("BUY", 3550, 3548, "1U")          # 160k+20k+14k = 194k / 800k = 0.24
    assert ok["status"] == "OK" and ok["stop_out_distance_usd"] == 10.0 and ok["stop_out_loss_toman"] == 800_000
    assert DM.stop_out_check("BUY", 3550, 3548, "0.5U")["stop_out_distance_usd"] == 10.0
    warn = DM.stop_out_check("BUY", 3550, 3545, "1U")        # 400k+20k+14k = 434k / 800k = 0.54
    assert warn["status"] == "WARN"
    rej = DM.stop_out_check("BUY", 3550, 3542.5, "1U")       # 600k+34k = 634k / 800k = 0.79 >= 0.75
    assert rej["status"] == "REJECT" and rej["loss_at_sl_toman"] == 634_000
    assert DM.stop_out_check("BUY", 3550, 3542.5, "1U", fee_scenario=DM.FEE_ENTRY_AND_EXIT)["loss_at_sl_toman"] == 648_000
    assert DM.stop_out_check("BUY", 3550, 3542.5, "1U", safety_margin=0.1)["status"] == "WARN"
