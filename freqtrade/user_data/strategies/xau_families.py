"""XauScalp: XAUUSD M5 scalping research strategy for freqtrade (dry backtests only).

Encodes (a) the xauscalper_zones.pine zone-entry logic (port: analysis/tv_signal_count_20261120.py)
and (b) the owner's style setups from analysis/real_trades_20261120/patterns.md:
  S2 momentum with H1 trend, S3 counter-trend bounce, L1 level-behind-stop gate, L2 NY-open skip, L3 ADR cap.
Every trade carries a hard SL and a TP as absolute prices inside enter_tag "SETUP|SL|TP|E".
Costs ($0.25 spread + $0.175 fee per 1U) are applied in the custom loss / report, fee=0 inside freqtrade.
Data: Dukascopy XAUUSD bid loaded as the pair XAU/USDT:USDT (dummy okx futures)."""
import os
from datetime import timedelta
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
from freqtrade.strategy import (IStrategy, IntParameter, DecimalParameter, CategoricalParameter,
                                stoploss_from_absolute)

TEH, NY, LON = 'Asia/Tehran', 'America/New_York', 'Europe/London'
TEHZ = ZoneInfo(TEH)
COST = 0.425  # $ per 1U round trip: 0.25 spread + 14000/80000 fee


def _ema(s, n):
    return s.ewm(span=n, adjust=False).mean()


def _atr(df, n=14):
    pc = df['close'].shift()
    tr = pd.concat([df['high'] - df['low'], (df['high'] - pc).abs(), (df['low'] - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def _trend(c):
    e1, e2 = _ema(c, 20), _ema(c, 50)
    return np.where((e1 > e2) & (c > e2), 1, np.where((e1 < e2) & (c < e2), -1, 0))


def _htf_trend(df, rule, mins):
    x = df.set_index('date')[['open', 'high', 'low', 'close']].resample(rule, label='left', closed='left').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'}).dropna()
    s = pd.DataFrame({'avail': x.index + pd.Timedelta(minutes=mins), 'tr': _trend(x['close'])})
    left = pd.DataFrame({'t': df['date'] + pd.Timedelta(minutes=5)})  # M5 candle close time
    m = pd.merge_asof(left, s, left_on='t', right_on='avail', direction='backward')
    return m['tr'].fillna(0).values


def _parse(tag):
    try:
        p = tag.split('|')
        return p[0], float(p[1]), float(p[2])
    except Exception:
        return None, None, None


class XauBase(IStrategy):
    INTERFACE_VERSION = 3
    timeframe = '5m'
    can_short = True
    startup_candle_count = 300
    process_only_new_candles = True
    use_custom_stoploss = True
    use_custom_roi = True
    stoploss = -0.004           # backstop ~ $16 at 4000; real SL comes from custom_stoploss
    minimal_roi = {"0": 10}     # TP handled by custom_roi
    trailing_stop = False
    trailing_stop_positive = None
    trailing_stop_positive_offset = 0.0
    trailing_only_offset_is_reached = False
    order_types = {'entry': 'limit', 'exit': 'market', 'stoploss': 'market', 'stoploss_on_exchange': False}
    unfilledtimeout = {'entry': 30, 'exit': 10, 'unit': 'minutes'}

    # ---- filters
    adr_max = IntParameter(80, 200, default=130, space='buy')            # L3 / pine ADR cap, 200 = off
    buf_max = DecimalParameter(5.0, 9.0, default=9.0, decimals=1, space='buy')  # SL + ATR <= buf_max (stop-out)
    l2_skip = CategoricalParameter([True, False], default=True, space='buy')   # skip 17:00-18:10 Tehran
    vol_k = DecimalParameter(1.5, 4.0, default=2.0, decimals=1, space='buy')
    # ---- exits (sell space)
    sl_atr = DecimalParameter(0.3, 1.2, default=0.5, decimals=2, space='sell')
    tp_r = DecimalParameter(0.6, 3.0, default=1.5, decimals=1, space='sell')     # quick TP for S2/S3 in R
    tp_atr = DecimalParameter(1.0, 3.0, default=3.0, decimals=1, space='sell')   # TP cap in ATR
    time_stop = IntParameter(20, 45, default=30, space='sell')
    # ---- protections
    slg_limit = IntParameter(2, 4, default=3, space='protection')
    cooldown = IntParameter(0, 6, default=1, space='protection')

    @property
    def protections(self):
        return [
            {"method": "CooldownPeriod", "stop_duration_candles": int(self.cooldown.value)},
            {"method": "StoplossGuard", "lookback_period_candles": 288, "trade_limit": int(self.slg_limit.value),
             "stop_duration_candles": 288, "only_per_pair": False},
        ]

    # ------------------------------------------------------------------ indicators (param-free)
    def populate_indicators(self, df: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df = df.copy()
        df['atr'] = _atr(df)
        df['tH1'] = _htf_trend(df, '60min', 60)
        df['tM15'] = _htf_trend(df, '15min', 15)
        d = df['date']
        ny, lo, te = d.dt.tz_convert(NY), d.dt.tz_convert(LON), d.dt.tz_convert(TEH)
        tc = (d + pd.Timedelta(minutes=5)).dt.tz_convert(TEH)   # candle close (= order time), Tehran
        tday = (ny.dt.tz_localize(None) + pd.Timedelta(hours=7)).dt.normalize()
        df['tday'] = tday
        g = df.groupby(tday)
        df['dH'] = g['high'].cummax(); df['dL'] = g['low'].cummin()
        day = g.agg(H=('high', 'max'), L=('low', 'min'))
        day['rng'] = day.H - day.L
        day['adr'] = day['rng'].shift(1).rolling(20, min_periods=5).mean()
        day['pdh'] = day.H.shift(1); day['pdl'] = day.L.shift(1)
        df['adr'] = tday.map(day['adr']); df['pdh'] = tday.map(day['pdh']); df['pdl'] = tday.map(day['pdl'])
        wk = tday.dt.to_period('W-SUN')
        wkd = df.groupby(wk).agg(H=('high', 'max'), L=('low', 'min'))
        df['pwh'] = wk.map(wkd.H.shift(1)); df['pwl'] = wk.map(wkd.L.shift(1))
        df['adr_used'] = (df.dH - df.dL) / df.adr * 100
        tm = te.dt.hour * 60 + te.dt.minute
        lm = lo.dt.hour * 60 + lo.dt.minute; nm = ny.dt.hour * 60 + ny.dt.minute
        masks = {'as': (tm >= 210) & (tm < 690), 'ln': (lm >= 420) & (lm < 1320) & (nm < 510), 'or': (lm >= 420) & (lm < 450)}
        for k, m in masks.items():
            df[k + 'H'] = df['high'].where(m).groupby(tday).cummax().groupby(tday).ffill()
            df[k + 'L'] = df['low'].where(m).groupby(tday).cummin().groupby(tday).ffill()
        nyo = df['open'].where((nm >= 510) & (nm < 515))
        df['nyO'] = nyo.groupby(tday).ffill()
        hl3 = (df.high + df.low + df.close) / 3
        df['vwap'] = (hl3 * df.volume).groupby(tday).cumsum() / df.volume.groupby(tday).cumsum().replace(0, np.nan)
        # vol expansion: ATR vs median of hourly ATR samples over 5 days
        hourly = df['atr'].where(d.dt.minute == 0)
        df['atr_med'] = hourly.rolling(1440, min_periods=24 * 12).median()
        df['mv15'] = df.close - df.close.shift(3)
        df['mv30'] = df.close - df.close.shift(6)
        # trading-hours flags at order time (candle close, Tehran)
        dow = tc.dt.dayofweek; hm = tc.dt.hour * 100 + tc.dt.minute
        open_ = ((dow <= 4) & (hm >= 700)) | ((dow >= 1) & (dow <= 5) & (hm < 30))
        fricut = ((dow == 4) & (hm >= 2330)) | ((dow == 5) & (hm < 30))
        df['tradeable'] = (open_ & ~fricut).astype(int)
        df['l2win'] = ((hm >= 1700) & (hm < 1810)).astype(int)
        df['month'] = tc.dt.strftime('%Y-%m')
        delta = df.close.diff()
        up = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean(); dn = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
        df['rsi'] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
        df['bbm'] = df.close.rolling(20).mean(); sd = df.close.rolling(20).std()
        df['bbu'] = df.bbm + 2 * sd; df['bbl'] = df.bbm - 2 * sd
        df['ema20'] = _ema(df.close, 20); df['ema50'] = _ema(df.close, 50)
        df['tM5'] = _trend(df.close)
        df['lon_min'] = lm; df['tehm'] = tc.dt.hour * 60 + tc.dt.minute
        orend = (lm >= 450)
        df['or_ready'] = (orend & df.orH.notna() & (lm < 450 + 240)).astype(int)
        df['hh6'] = df.high.rolling(6).max().shift(1); df['ll6'] = df.low.rolling(6).min().shift(1)
        self._zones(df)
        return df

    def _zones(self, df):
        n = len(df)
        cols = ['pdh', 'pdl', 'pwh', 'pwl', 'asH', 'asL', 'lnH', 'lnL', 'orH', 'orL', 'nyO', 'vwap']
        L = df[cols].to_numpy(); H_ = df.high.to_numpy(); Lo = df.low.to_numpy(); C = df.close.to_numpy()
        A = df.atr.to_numpy()
        out = {k: np.full(n, np.nan) for k in ['zlE', 'zlS', 'zlN', 'zlId', 'zsE', 'zsS', 'zsN', 'zsId', 'lvA', 'lvB']}
        for i in range(n):
            a = A[i]
            if not a == a:
                continue
            hw = max(0.25 * a, 1.0)
            lv = [x for x in L[i] if x == x]
            rb = np.floor(C[i] / 50) * 50
            lv += [rb + k * 50 for k in (-1, 0, 1, 2)]
            lv.sort()
            above = [x for x in lv if x > C[i]]; below = [x for x in lv if x < C[i]]
            if above: out['lvA'][i] = above[0]
            if below: out['lvB'][i] = below[-1]
            zLo, zHi, zMn, zMx = [], [], [], []
            for p in lv:
                if zLo and p - hw <= zHi[-1]:
                    zHi[-1] = p + hw; zMx[-1] = p
                else:
                    zLo.append(p - hw); zHi.append(p + hw); zMn.append(p); zMx.append(p)
            nz = len(zLo)
            if nz < 2:
                continue
            for j in range(nz - 1, -1, -1):
                if zLo[j] <= C[i] and Lo[i] <= zHi[j]:
                    if j < nz - 1:
                        E = min(C[i], zHi[j]); out['zlE'][i] = E; out['zlS'][i] = E - zLo[j]
                        out['zlN'][i] = zMn[j + 1]; out['zlId'][i] = zMn[j]
                    break
            for j in range(nz):
                if zHi[j] >= C[i] and H_[i] >= zLo[j]:
                    if j > 0:
                        E = max(C[i], zLo[j]); out['zsE'][i] = E; out['zsS'][i] = zHi[j] - E
                        out['zsN'][i] = zMx[j - 1]; out['zsId'][i] = zMx[j]
                    break
        for k, v in out.items():
            df[k] = v

    # ------------------------------------------------------------------ entries
    def _base_ok(self, df):
        ok = (df.tradeable == 1) & df.atr.notna() & df.adr.notna()
        # entry window from config (data is loaded from mid-July so ADR20 / ATR medians are warm)
        tf, tt = self.config.get('trade_from'), self.config.get('trade_to')
        if tf:
            ok &= df.date >= pd.Timestamp(tf, tz='UTC')
        if tt:
            ok &= df.date < pd.Timestamp(tt, tz='UTC')
        ok &= ~(df.atr > self.vol_k.value * df.atr_med)
        if self.adr_max.value < 200:
            ok &= ~(df.adr_used > self.adr_max.value)
        if self.l2_skip.value:
            ok &= df.l2win == 0
        return ok

    def _finish(self, df, mask, side, setup, E, d, tpD, rr_min=0.0):
        """common SL/TP gates; side +1 long / -1 short. d = SL distance $, tpD = TP distance $."""
        a = df.atr
        rem = (df.adr - (df.dH - df.dL)).clip(lower=0)
        tpD = np.minimum(np.minimum(tpD, self.tp_atr.value * a), rem)
        ok = mask & d.notna() & tpD.notna() & (d + a <= self.buf_max.value) & (tpD >= 1.0)
        rr = (tpD * 80000 - 14000) / (d * 80000 + 14000)
        ok &= (rr >= rr_min) & (rr <= 8)
        ok &= (df.enter_long != 1) & (df.enter_short != 1)
        col = 'enter_long' if side == 1 else 'enter_short'
        sl = E - side * d; tp = E + side * tpD
        tag = setup + ('L' if side == 1 else 'S') + '|' + sl.round(3).astype(str) + '|' + tp.round(3).astype(str) + '|' + E.round(3).astype(str)
        df.loc[ok, col] = 1
        df.loc[ok, 'enter_tag'] = tag[ok]

    def _sl(self, df, struct=None):
        d = np.maximum(1.0, self.sl_atr.value * df.atr)
        if struct is not None:
            d = np.maximum(d, struct + 0.5)
        return d

    def signals(self, df, base):
        raise NotImplementedError

    def populate_entry_trend(self, df: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df['enter_long'] = 0; df['enter_short'] = 0; df['enter_tag'] = None
        self.signals(df, self._base_ok(df))
        return df

    def populate_exit_trend(self, df: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        df['exit_long'] = 0; df['exit_short'] = 0
        return df

    # ------------------------------------------------------------------ callbacks
    def custom_entry_price(self, pair, trade, current_time, proposed_rate, entry_tag, side, **kwargs):
        setup, _, _ = _parse(entry_tag or '')
        if setup and setup.startswith('Z'):
            return float(entry_tag.split('|')[3])  # resting limit at the zone edge, 30 min validity
        return proposed_rate

    def custom_stoploss(self, pair, trade, current_time, current_rate, current_profit, after_fill, **kwargs):
        _, sl, _ = _parse(trade.enter_tag or '')
        if sl is None:
            return None
        if (not trade.is_short and sl >= current_rate) or (trade.is_short and sl <= current_rate):
            return 0.0001
        return stoploss_from_absolute(sl, current_rate, is_short=trade.is_short, leverage=trade.leverage)

    def custom_roi(self, pair, trade, current_time, trade_duration, entry_tag, side, **kwargs):
        if trade_duration < 1:      # 60 s minimum hold (SL exempt)
            return 10.0
        _, _, tp = _parse(entry_tag or '')
        if tp is None:
            return None
        r = (tp - trade.open_rate) / trade.open_rate * (-1 if trade.is_short else 1)
        return max(r, 0.00001)

    def custom_exit(self, pair, trade, current_time, current_rate, current_profit, **kwargs):
        if current_time - trade.open_date_utc >= timedelta(minutes=int(self.time_stop.value)):
            return 'time_stop'
        tc = current_time.astimezone(TEHZ)
        if tc.hour == 0 and 25 <= tc.minute < 35:
            return 'session_close'
        return None


def _new(m):
    return m & ~m.shift(1, fill_value=False)


def _sides(mirror):
    return (1, -1) if mirror else (-1,)


class XauZone(XauBase):
    """Pine zone entry: limit at the zone edge, in the H1+M15 trend, TP at next zone, R:R floor."""
    rr_min = DecimalParameter(0.5, 2.0, default=1.5, decimals=1, space='buy')

    def signals(self, df, base):
        a = df.atr
        for side, p in ((1, 'zl'), (-1, 'zs')):
            raw = (df.tH1 == side) & (df.tM15 == side) & df[p + 'E'].notna()
            new = raw & (~raw.shift(1, fill_value=False) | (df[p + 'Id'] != df[p + 'Id'].shift(1)))
            E = df[p + 'E']; d = self._sl(df, df[p + 'S'])
            tpD = side * ((df[p + 'N'] - side * np.maximum(0.3, 0.1 * a)) - E)
            room = side * (df[p + 'N'] - E) >= 2 * d
            self._finish(df, base & new & room, side, 'Z', E, d, tpD, self.rr_min.value)


class XauS2(XauBase):
    """Owner style S2: momentum entry with the H1 trend after a >= k*ATR 15-min move; L1 gate: a level within l1*ATR behind the stop."""
    s2_k = DecimalParameter(0.5, 2.0, default=1.0, decimals=1, space='buy')
    l1_k = DecimalParameter(0.3, 2.0, default=0.8, decimals=1, space='buy')
    mirror = CategoricalParameter([True, False], default=True, space='buy')

    def signals(self, df, base):
        a, C = df.atr, df.close
        for side in _sides(self.mirror.value):
            beh = (df.lvA - C) if side == -1 else (C - df.lvB)
            m = base & (beh <= self.l1_k.value * a) & (df.tH1 == side) & (side * df.mv15 >= self.s2_k.value * a)
            d = self._sl(df, beh)
            self._finish(df, _new(m), side, 'S2', C, d, self.tp_r.value * d)


class XauS3(XauBase):
    """Owner style S3: bounce against the H1 trend after a 30-min counter move; L1 gate."""
    s3_k = DecimalParameter(0.0, 1.5, default=0.3, decimals=1, space='buy')
    l1_k = DecimalParameter(0.3, 2.0, default=0.8, decimals=1, space='buy')
    mirror = CategoricalParameter([True, False], default=True, space='buy')

    def signals(self, df, base):
        a, C = df.atr, df.close
        for tr in _sides(self.mirror.value):
            s = -tr
            beh = (C - df.lvB) if s == 1 else (df.lvA - C)
            m = base & (beh <= self.l1_k.value * a) & (df.tH1 == tr) & (s * df.mv30 > self.s3_k.value * a)
            d = self._sl(df, beh)
            self._finish(df, _new(m), s, 'S3', C, d, self.tp_r.value * d)


class XauPullback(XauBase):
    """EMA trend pullback: H1 and M15 trend agree; M5 bar dips to EMA20 (within pb_k*ATR) and closes back on the trend side."""
    pb_k = DecimalParameter(0.0, 0.6, default=0.2, decimals=1, space='buy')
    need_m5 = CategoricalParameter([True, False], default=False, space='buy')

    def signals(self, df, base):
        a, C, e = df.atr, df.close, df.ema20
        for side in (1, -1):
            tr = (df.tH1 == side) & (df.tM15 == side)
            if self.need_m5.value:
                tr &= df.tM5 == side
            touch = (df.low <= e + self.pb_k.value * a) if side == 1 else (df.high >= e - self.pb_k.value * a)
            back = (C > e) & (C > df.open) if side == 1 else (C < e) & (C < df.open)
            struct = (C - df.low) if side == 1 else (df.high - C)
            d = self._sl(df, struct)
            self._finish(df, _new(base & tr & touch & back), side, 'PB', C, d, self.tp_r.value * d)


class XauORB(XauBase):
    """London opening-range breakout (OR = 07:00-07:30 London = 10:30-11:00 Tehran), first close beyond OR within 4 h."""
    orb_buf = DecimalParameter(0.0, 1.0, default=0.2, decimals=1, space='buy')   # x ATR beyond OR edge
    orb_trend = CategoricalParameter([True, False], default=False, space='buy')
    orb_max = DecimalParameter(1.0, 4.0, default=3.0, decimals=1, space='buy')   # max OR size in ATR

    def signals(self, df, base):
        a, C = df.atr, df.close
        ok = base & (df.or_ready == 1) & ((df.orH - df.orL) <= self.orb_max.value * a)
        for side in (1, -1):
            lvl = df.orH if side == 1 else df.orL
            brk = side * (C - lvl) > self.orb_buf.value * a
            first = brk & ~(brk.groupby(df.tday).cummax().shift(1, fill_value=False) & (df.tday == df.tday.shift(1)))
            m = ok & first
            if self.orb_trend.value:
                m &= df.tH1 == side
            struct = side * (C - lvl)
            d = self._sl(df, struct)
            self._finish(df, m, side, 'ORB', C, d, self.tp_r.value * d)


class XauVWAP(XauBase):
    """VWAP reversion: close stretched >= vw_k*ATR from day VWAP and the bar reverses toward it; TP = min(tp_r*SL, distance to VWAP)."""
    vw_k = DecimalParameter(1.0, 4.0, default=2.0, decimals=1, space='buy')
    vw_tp_frac = DecimalParameter(0.5, 1.0, default=1.0, decimals=1, space='buy')

    def signals(self, df, base):
        a, C, v = df.atr, df.close, df.vwap
        for side in (1, -1):
            stretch = side * (v - C) >= self.vw_k.value * a
            rev = (C > df.open) if side == 1 else (C < df.open)
            struct = (C - df.low) if side == 1 else (df.high - C)
            d = self._sl(df, struct)
            tpD = np.minimum(self.tp_r.value * d, self.vw_tp_frac.value * side * (v - C))
            self._finish(df, _new(base & stretch & rev), side, 'VW', C, d, tpD)


class XauMR(XauBase):
    """RSI/Bollinger mean reversion: close outside BB(20,2) with RSI14 beyond rsi_lo/(100-rsi_lo), next bar enters toward the mid; TP = min(tp_r*SL, to BB mid)."""
    rsi_lo = IntParameter(15, 35, default=25, space='buy')
    mr_trend = CategoricalParameter([True, False], default=False, space='buy')   # only with H1 trend

    def signals(self, df, base):
        C = df.close
        for side in (1, -1):
            ext = (C < df.bbl) & (df.rsi < self.rsi_lo.value) if side == 1 else (C > df.bbu) & (df.rsi > 100 - self.rsi_lo.value)
            m = base & ext
            if self.mr_trend.value:
                m &= df.tH1 == side
            struct = (C - df.low) if side == 1 else (df.high - C)
            d = self._sl(df, struct)
            tpD = np.minimum(self.tp_r.value * d, side * (df.bbm - C))
            self._finish(df, _new(m), side, 'MR', C, d, tpD)


class XauRandom(XauBase):
    """Random-entry control: same hours/filters, random side, same exit machinery.
    Env: RC_P (entry prob per eligible bar), RC_SL (SL ATR mult), RC_TPR (TP in R), RC_TS (time stop), RC_SEED."""
    def signals(self, df, base):
        p = float(os.environ.get('RC_P', '0.01')); seed = int(os.environ.get('RC_SEED', '1'))
        self.sl_atr.value = float(os.environ.get('RC_SL', '0.5')); self.tp_r.value = float(os.environ.get('RC_TPR', '1.5'))
        self.time_stop.value = int(os.environ.get('RC_TS', '30'))
        rng = np.random.default_rng(seed)
        u = rng.random(len(df)); sd = rng.random(len(df))
        C = df.close
        for side in (1, -1):
            m = base & pd.Series((u < p) & ((sd < 0.5) if side == 1 else (sd >= 0.5)), index=df.index)
            d = self._sl(df)
            self._finish(df, m, side, 'RND', C, d, self.tp_r.value * d)
