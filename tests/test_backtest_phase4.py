"""Phase 4 replay: point-in-time data and look-ahead leakage tests (historical simulation harness)."""
import os, sys
import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backtest", "phase4"))
ARCHIVE = "/workspace/data/gold_1m/xauusd_1m.parquet"
pytestmark = pytest.mark.skipif(not os.path.exists(ARCHIVE), reason="Dukascopy archive not on this machine")

# two instants where the live engines produced an approved signal in the April 2024 replay, plus quiet ones
TS = ["2024-04-03 12:02", "2024-04-11 16:02", "2024-04-08 05:32", "2024-04-10 18:47", "2024-04-12 09:17"]


@pytest.fixture(scope="module")
def world():
    from data import load_hist, Market
    import engine as E, broker_daryagold as DG
    m1 = load_hist(start="2024-02-01", end="2024-04-20")
    return m1, Market(m1), E, DG.load_config(equity=2954400)


def _strip(ev):
    return {k: v for k, v in ev.items()}


def test_point_in_time_frames_equal_fresh_resample(world):
    from data import resample, TFS
    m1, M, _, _ = world
    for ts in TS:
        t = pd.Timestamp(ts, tz="UTC")
        trunc = m1[m1.index <= t - pd.Timedelta(minutes=1)]
        for tf, rule in TFS.items():
            a = M.bars_at(tf, t)
            b = resample(trunc, rule)
            b = b[b.index >= a.index[0]]
            pd.testing.assert_frame_equal(a, b, check_freq=False)
        assert M.bars_at("1m", t).index[-1] <= t - pd.Timedelta(minutes=1)


def test_no_lookahead_future_deleted_or_perturbed(world):
    from data import Market
    m1, M, E, cfg = world
    rng = np.random.default_rng(7)
    approved = 0
    for ts in TS:
        t = pd.Timestamp(ts, tz="UTC")
        base = E.evaluate(M, t, cfg)
        approved += base["status"].startswith("APPROVED")
        cut = m1[m1.index < t]
        assert E.evaluate(Market(cut), t, cfg) == base, f"future deletion changed the decision at {ts}"
        noisy = m1.copy()
        fut = noisy.index >= t - pd.Timedelta(minutes=1) + pd.Timedelta(minutes=1)
        shift = rng.normal(0, 25, fut.sum())
        for c in ("o_b", "h_b", "l_b", "c_b", "o_a", "h_a", "l_a", "c_a"):
            noisy.loc[fut, c] = noisy.loc[fut, c].to_numpy() + shift
        assert E.evaluate(Market(noisy), t, cfg) == base, f"future perturbation changed the decision at {ts}"
    assert approved >= 1          # the test covers at least one approved signal, not only NO_TRADE


def test_live_modules_restored_after_replay(world):
    import levels as LV, bias as BI, regime as REG, broker_daryagold as DG, m5lib
    _, M, E, cfg = world
    before = (LV.load_bars, BI.load_bars, REG.load_bars, m5lib.load_bars, DG.daily_loss_veto)
    E.evaluate(M, pd.Timestamp(TS[0], tz="UTC"), cfg)
    assert (LV.load_bars, BI.load_bars, REG.load_bars, m5lib.load_bars, DG.daily_loss_veto) == before


def test_order_sim_60s_rule_and_costs():
    import sim
    idx = pd.date_range("2024-04-03 12:00", periods=8, freq="1min", tz="UTC")
    # BUY limit 100: fills minute 0; TP 102 touched in minutes 0-1 (deferred), again in minute 3 (taken)
    bars = pd.DataFrame({"o_b": [100.5, 101, 101, 101, 101, 101, 101, 101], "h_b": [102.5, 102.2, 101.5, 102.1, 101, 101, 101, 101],
                         "l_b": [99.9, 100.6, 100.6, 100.6, 100.6, 100.6, 100.6, 100.6], "c_b": [101] * 8}, index=idx)
    sig = {"side": "BUY", "entry": 100.0, "sl": 99.0, "tp": 102.0, "unit": "full_unit"}
    r = sim.simulate_order(bars, sig, idx[0], idx[-1] + pd.Timedelta(minutes=1))
    assert r["filled"] and r["exit_type"] == "tp" and r["tp_deferred"] == 2 and r["exit_at"] == idx[3]
    assert r["gross"] == 160000 and r["net"] == 160000 - 20000 - 14000          # fee once + $0.25 spread
    assert abs(r["R"] - (126000 / (80000 + 20000 + 14000))) < 1e-9
    # SL and TP in the same bar -> SL; gap through SL fills at the open
    bars2 = bars.copy(); bars2.iloc[2] = [98.5, 102.5, 98.0, 99]
    r2 = sim.simulate_order(bars2, sig, idx[0], idx[-1] + pd.Timedelta(minutes=1))
    assert r2["exit_type"] == "sl" and r2["exit"] == 98.5 and r2["net"] == -120000 - 20000 - 14000
    # never filled -> expired, no P&L
    r3 = sim.simulate_order(bars, dict(sig, entry=95.0, sl=94.0), idx[0], idx[-1] + pd.Timedelta(minutes=1))
    assert not r3["filled"] and "net" not in r3
