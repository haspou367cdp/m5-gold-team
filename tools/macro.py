#!/usr/bin/env python3
"""macro.py - DXY, US 2Y / 10Y nominal, 10Y real yield, 5Y/10Y breakevens, plus regime / ADR helpers.

Free sources, short timeouts, 10-minute cache, never hangs the brief.
  * DXY: Yahoo DX-Y.NYB (fallback DX=F, then EURUSD proxy)
  * US 10Y nominal: Yahoo ^TNX (fallback FRED DGS10, lagged)
  * US 2Y: Yahoo 2YY=F (2-Year Yield Futures, not the cash Treasury) with FRED DGS2 as the official lagged cash series.
    Yahoo ^IRX is the 13-week bill and is NOT used as a 2Y proxy.
  * 10Y real yield: FRED DFII10 (daily, lagged)
  * 5Y / 10Y inflation breakevens: FRED T5YIE / T10YIE (daily, lagged)

If a series cannot be fetched, it is marked "در دسترس نیست" (no exception, no block).
usage: python3 macro.py [--no-fetch] [--ttl 600]
Signal-only research. Not financial advice."""
import argparse, json, os, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, "/workspace/m5-gold-team/tools")
from m5lib import DATA, TEH, teh as teh_fmt

CACHE = f"{DATA}/macro.json"
TTL = 600                 # seconds
REQ_TIMEOUT = 6           # per HTTP request
BUDGET = 10               # overall fetch budget (seconds)
UA = "Mozilla/5.0 (compatible; M5GoldBrief/1.0; research)"

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _http_get(url, timeout=REQ_TIMEOUT):
    """stdlib HTTP/1.1 GET; returns (status, text) or (None, err)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(2_000_000)
            return r.status, raw.decode("utf-8", "replace")
    except Exception as e:
        return None, str(e)

def _teh_from_unix(ts):
    if ts is None: return None
    try:
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(TEH)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return None

def _now_teh():
    return datetime.now(TEH).strftime("%Y-%m-%d %H:%M:%S")

# ---------------------------------------------------------------------------
# Yahoo (DXY, 10Y nominal, EURUSD fallback)
# ---------------------------------------------------------------------------
def _yahoo_chart(symbol):
    q = urllib.parse.quote(symbol, safe="")
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{q}"
           f"?interval=1m&range=1d&includePrePost=false")
    status, body = _http_get(url)
    if status != 200:
        # query2 mirror
        url2 = url.replace("query1.", "query2.")
        status, body = _http_get(url2)
    if status != 200:
        return None, f"yahoo {symbol}: HTTP {status} {body[:120] if body else ''}"
    try:
        d = json.loads(body)
        res = ((d.get("chart") or {}).get("result") or [None])[0]
        if not res: return None, f"yahoo {symbol}: empty result"
        meta = res.get("meta") or {}
        ts = res.get("timestamp") or []
        q0 = ((res.get("indicators") or {}).get("quote") or [{}])[0]
        closes = q0.get("close") or []
        highs = [x for x in (q0.get("high") or []) if x is not None]
        lows = [x for x in (q0.get("low") or []) if x is not None]
        pairs = [(t, c) for t, c in zip(ts, closes) if c is not None]
        last = pairs[-1][1] if pairs else meta.get("regularMarketPrice")
        last_ts = pairs[-1][0] if pairs else meta.get("regularMarketTime")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose") or meta.get("regularMarketPreviousClose")
        chg = (last - prev) if (last is not None and prev) else None
        pct = (100.0 * chg / prev) if (chg is not None and prev) else None
        return {
            "symbol": symbol,
            "last": round(float(last), 4) if last is not None else None,
            "prev_close": round(float(prev), 4) if prev else None,
            "change": round(float(chg), 4) if chg is not None else None,
            "change_pct": round(float(pct), 4) if pct is not None else None,
            "day_high": round(float(max(highs)), 4) if highs else None,
            "day_low": round(float(min(lows)), 4) if lows else None,
            "as_of_tehran": _teh_from_unix(last_ts),
            "source": f"Yahoo Finance {symbol}",
        }, None
    except Exception as e:
        return None, f"yahoo {symbol}: {e}"

def _fetch_dxy():
    for sym, kind in (("DX-Y.NYB", "DXY"), ("DX=F", "DX=F (dollar futures, not the cash index)")):
        data, err = _yahoo_chart(sym)
        if data and data.get("last") is not None:
            data["kind"] = kind
            data["proxy"] = kind != "DXY"
            return data
        last_err = err
    # EURUSD as inverse proxy (up EURUSD ≈ weaker dollar ≈ less bearish for gold)
    data, err = _yahoo_chart("EURUSD=X")
    if data and data.get("last") is not None:
        data["kind"] = "EURUSD proxy"
        data["proxy"] = True
        data["note"] = "DXY در دسترس نبود؛ EURUSD به‌عنوان پروکسی معکوس دلار گزارش می‌شود."
        return data
    return {"unavailable": True, "error": last_err or err or "DXY/EURUSD unavailable", "kind": "DXY"}

def _fetch_us10y():
    data, err = _yahoo_chart("^TNX")
    if data and data.get("last") is not None:
        data["kind"] = "US10Y nominal"
        data["unit"] = "percent"
        # ^TNX is quoted in yield percent (e.g. 5.10)
        return data
    # lagged official daily close
    row, ferr = _fred_last("DGS10")
    if row:
        row["kind"] = "US10Y nominal"
        row["lagged"] = True
        row["source"] = "FRED DGS10 (daily, lagged)"
        return row
    return {"unavailable": True, "error": err or ferr or "US10Y unavailable", "kind": "US10Y nominal"}

def _fred_last(series):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    status, body = _http_get(url, timeout=REQ_TIMEOUT)
    if status != 200 or not body or body.lstrip().startswith("<"):
        return None, f"FRED {series}: HTTP {status} {(body or '')[:120]}"
    last = prev = None
    for line in body.strip().splitlines()[1:]:
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2: continue
        date, val = parts[0], parts[1]
        if val in (".", "", "NA"): continue
        try:
            v = float(val)
        except ValueError:
            continue
        prev = last
        last = {"last": v, "as_of_date": date, "prev": prev["last"] if prev else None}
    if not last:
        return None, f"FRED {series}: no rows"
    chg = (last["last"] - last["prev"]) if last.get("prev") is not None else None
    return {
        "last": round(last["last"], 4),
        "prev_close": round(last["prev"], 4) if last.get("prev") is not None else None,
        "change": round(chg, 4) if chg is not None else None,
        "as_of_date": last["as_of_date"],
        "as_of_tehran": None,
        "lagged": True,
        "source": f"FRED {series} (daily, lagged)",
        "unit": "percent",
    }, None

def _fetch_real10y():
    row, err = _fred_last("DFII10")
    if row:
        row["kind"] = "US10Y real (TIPS)"
        row["lagged"] = True
        return row
    return {"unavailable": True, "error": err or "DFII10 unavailable", "kind": "US10Y real (TIPS)", "lagged": True}

def _fred_many(ids, start="2024-01-01"):
    """One CSV for several FRED series. Last non-null per column is kept (dates can be staggered)."""
    q = ",".join(ids)
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={q}&cosd={start}"
    status, body = _http_get(url, timeout=REQ_TIMEOUT)
    if status != 200 or not body or body.lstrip().startswith("<"):
        # full history as a fallback (slower, larger)
        url2 = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={q}"
        status, body = _http_get(url2, timeout=REQ_TIMEOUT)
    if status != 200 or not body or body.lstrip().startswith("<"):
        return None, f"FRED batch {q}: HTTP {status} {(body or '')[:120]}"
    lines = body.strip().splitlines()
    if len(lines) < 2:
        return None, f"FRED batch {q}: no rows"
    header = [h.strip() for h in lines[0].split(",")]
    # first col is DATE / observation_date
    cols = header[1:]
    last, prev = {c: None for c in cols}, {c: None for c in cols}
    for line in lines[1:]:
        parts = [p.strip() for p in line.split(",")]
        if not parts:
            continue
        date = parts[0]
        for i, c in enumerate(cols):
            val = parts[i + 1] if i + 1 < len(parts) else ""
            if val in (".", "", "NA"):
                continue
            try:
                v = float(val)
            except ValueError:
                continue
            prev[c] = last[c]
            last[c] = {"last": v, "as_of_date": date, "prev": (prev[c]["last"] if prev[c] else None)}
    out = {}
    for c in cols:
        row = last[c]
        if not row:
            out[c] = {"unavailable": True, "error": f"FRED {c}: no rows", "lagged": True, "source": f"FRED {c} (daily, lagged)"}
            continue
        chg = (row["last"] - row["prev"]) if row.get("prev") is not None else None
        out[c] = {
            "last": round(row["last"], 4),
            "prev_close": round(row["prev"], 4) if row.get("prev") is not None else None,
            "change": round(chg, 4) if chg is not None else None,
            "as_of_date": row["as_of_date"],
            "as_of_tehran": None,
            "lagged": True,
            "source": f"FRED {c} (daily, lagged)",
            "unit": "percent",
        }
    return out, None

def _empty(kind, lagged=False, err=None):
    d = {"unavailable": True, "error": err or "unavailable", "kind": kind}
    if lagged:
        d["lagged"] = True
    return d

def _fetch_fred_stack():
    """DFII10, DGS2, T5YIE, T10YIE, DGS10 in one request."""
    ids = ["DFII10", "DGS2", "T5YIE", "T10YIE", "DGS10"]
    data, err = _fred_many(ids)
    if not data:
        return {k: _empty(k, lagged=True, err=err) for k in ids}
    # stamp kinds
    kinds = {
        "DFII10": "US10Y real (TIPS)",
        "DGS2": "US2Y nominal cash",
        "T5YIE": "5Y inflation breakeven",
        "T10YIE": "10Y inflation breakeven",
        "DGS10": "US10Y nominal",
    }
    for k, kind in kinds.items():
        row = data.get(k) or _empty(kind, lagged=True, err=f"FRED {k} missing")
        row["kind"] = kind
        row["lagged"] = True
        data[k] = row
    return data

def _as_of_age_hours(block):
    """Hours since the series timestamp (Tehran clock or FRED date). None if unknown."""
    ts = block.get("as_of_tehran")
    if ts:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
            try:
                dt = datetime.strptime(ts, fmt).replace(tzinfo=TEH)
                return (datetime.now(TEH) - dt).total_seconds() / 3600.0
            except ValueError:
                continue
    d = block.get("as_of_date")
    if d:
        try:
            dt = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=TEH)
            return (datetime.now(TEH) - dt).total_seconds() / 3600.0
        except ValueError:
            return None
    return None

def _fetch_us2y_yahoo():
    """Yahoo 2YY=F is 2-Year Yield Futures, not the cash 2Y Treasury. Never use ^IRX (13-week bill).
    Reject prints older than 4 days — an expired front contract can sit unchanged for weeks."""
    data, err = _yahoo_chart("2YY=F")
    if data and data.get("last") is not None:
        age_h = _as_of_age_hours(data)
        if age_h is not None and age_h > 96:
            return _empty("US2Y yield futures",
                          err=f"2YY=F last print is {age_h/24:.1f} days old (likely an expired contract); not used")
        data["kind"] = "US2Y yield futures"
        data["unit"] = "percent"
        data["proxy"] = True
        data["lagged"] = False
        data["note"] = "بازده آتی ۲ساله (Yahoo 2YY=F)، نه بازده نقدی خزانه؛ سری رسمی FRED DGS2 با تأخیر است."
        return data
    return _empty("US2Y yield futures", err=err or "2YY=F unavailable")

# ---------------------------------------------------------------------------
# cache + fetch
# ---------------------------------------------------------------------------
def _read_cache():
    try:
        with open(CACHE) as f: return json.load(f)
    except Exception:
        return None

def _age_s(doc):
    if not doc or not doc.get("fetched_at_unix"): return 1e12
    return time.time() - float(doc["fetched_at_unix"])

def fetch(force=False, ttl=TTL):
    """Return a macro document. Uses cache if younger than ttl seconds.
    On fetch failure, returns stale cache (flagged) if < 24h old, else unavailable stubs."""
    cached = _read_cache()
    if cached and not force and _age_s(cached) <= ttl and cached.get("ok"):
        cached["from_cache"] = True
        return cached
    t0 = time.time()
    dxy = us10y = us2y_y = fred = None
    errors = []
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {
            ex.submit(_fetch_dxy): "dxy",
            ex.submit(_fetch_us10y): "us10y",
            ex.submit(_fetch_us2y_yahoo): "us2y",
            ex.submit(_fetch_fred_stack): "fred",
        }
        done, not_done = wait(futs, timeout=BUDGET)
        for fut in not_done:
            fut.cancel()
            errors.append(f"{futs[fut]} timed out after {BUDGET}s")
        for fut in done:
            key = futs[fut]
            try:
                val = fut.result()
            except Exception as e:
                val = {"unavailable": True, "error": str(e), "kind": key}
            if key == "dxy": dxy = val
            elif key == "us10y": us10y = val
            elif key == "us2y": us2y_y = val
            else: fred = val
    dxy = dxy or _empty("DXY", err="timeout")
    us10y = us10y or _empty("US10Y nominal", err="timeout")
    us2y_y = us2y_y or _empty("US2Y yield futures", err="timeout")
    fred = fred or {}
    real = fred.get("DFII10") or _empty("US10Y real (TIPS)", lagged=True, err="timeout")
    be5 = fred.get("T5YIE") or _empty("5Y inflation breakeven", lagged=True, err="timeout")
    be10 = fred.get("T10YIE") or _empty("10Y inflation breakeven", lagged=True, err="timeout")
    dgs2 = fred.get("DGS2") or _empty("US2Y nominal cash", lagged=True, err="timeout")
    # 10Y: prefer live Yahoo; fill from FRED DGS10 if Yahoo failed
    if us10y.get("unavailable") and fred.get("DGS10") and not fred["DGS10"].get("unavailable"):
        us10y = dict(fred["DGS10"])
        us10y["kind"] = "US10Y nominal"
    # 2Y: prefer 2YY=F (labelled as futures); always attach official lagged DGS2
    if us2y_y and not us2y_y.get("unavailable") and us2y_y.get("last") is not None:
        us2y = dict(us2y_y)
        us2y["official_fred"] = dgs2 if not dgs2.get("unavailable") else None
    elif not dgs2.get("unavailable") and dgs2.get("last") is not None:
        us2y = dict(dgs2)
        us2y["kind"] = "US2Y nominal cash"
        us2y["proxy"] = False
        us2y["note"] = "بازده نقدی ۲ساله FRED DGS2 (روزانه، با تأخیر). Yahoo 2YY=F در دسترس نبود."
    else:
        us2y = _empty("US2Y", lagged=True, err=(us2y_y or {}).get("error") or dgs2.get("error"))
    for block in (dxy, us10y, us2y, real, be5, be10):
        if block.get("unavailable") and block.get("error"):
            errors.append(block["error"])
    ok = not all(b.get("unavailable") for b in (dxy, us10y, us2y, real, be5, be10))
    doc = {
        "ok": ok,
        "from_cache": False,
        "stale": False,
        "fetched_at_tehran": _now_teh(),
        "fetched_at_unix": time.time(),
        "elapsed_s": round(time.time() - t0, 2),
        "dxy": dxy,
        "us10y": us10y,
        "us2y": us2y,
        "real10y": real,
        "be5": be5,
        "be10": be10,
        "gold_lean": gold_lean(dxy, us10y, real, us2y=us2y),
        "errors": errors,
    }
    if ok:
        try:
            os.makedirs(DATA, exist_ok=True)
            tmp = CACHE + ".tmp"
            with open(tmp, "w") as f: json.dump(doc, f, ensure_ascii=False, indent=1, default=str)
            os.replace(tmp, CACHE)
        except Exception:
            pass
        return doc
    # all failed: reuse stale cache if < 24h
    if cached and _age_s(cached) < 86400:
        cached = dict(cached)
        cached["from_cache"] = True
        cached["stale"] = True
        cached["errors"] = errors + [f"fetch failed; using cache age {int(_age_s(cached))}s"]
        cached["gold_lean"] = gold_lean(cached.get("dxy") or {}, cached.get("us10y") or {},
                                        cached.get("real10y") or {}, us2y=cached.get("us2y") or {})
        return cached
    return doc


def gold_lean(dxy, us10y, real, us2y=None):
    """Simple backdrop for gold: rising dollar / yields = bearish, falling = bullish.
    Intraday change is preferred; lagged daily change is used only as backdrop."""
    votes, why = [], []
    def vote(block, name, lo, hi, lagged_note=False):
        if not block or block.get("unavailable") or block.get("last") is None:
            return
        chg = block.get("change")
        if chg is None:
            return
        if abs(chg) < lo:
            tag = "flat"
            v = 0
        elif chg > 0:
            tag, v = "up", -1
        else:
            tag, v = "down", +1
        lag = " (با تأخیر)" if (block.get("lagged") or lagged_note) else ""
        votes.append(v)
        why.append(f"{name} {tag}{lag}")
    # DXY / EURUSD proxy: for EURUSD, up is *weaker* dollar → flip sign
    if dxy and not dxy.get("unavailable"):
        if dxy.get("kind") == "EURUSD proxy":
            # flip: EURUSD up = dollar down = gold-friendly = +1
            chg = dxy.get("change")
            if chg is not None:
                fake = dict(dxy)
                fake["change"] = -chg
                vote(fake, "EURUSD (پروکسی دلار)", 0.0005, 0.0005)
        else:
            vote(dxy, "DXY", 0.02, 0.02)   # 0.02 index point ≈ flat
    vote(us2y, "بازده ۲ساله", 0.01, 0.01, lagged_note=bool((us2y or {}).get("lagged")))
    vote(us10y, "بازده اسمی ۱۰ساله", 0.01, 0.01, lagged_note=bool((us10y or {}).get("lagged")))
    vote(real, "بازده واقعی ۱۰ساله", 0.01, 0.01, lagged_note=True)
    if not votes:
        return {"lean": None, "fa": "در دسترس نیست", "why": why}
    s = sum(votes)
    if s <= -1: lean, fa = "bearish", "نزولی"
    elif s >= 1: lean, fa = "bullish", "صعودی"
    else: lean, fa = "neutral", "خنثی / مختلط"
    return {"lean": lean, "fa": fa, "why": why, "votes": votes}

# ---------------------------------------------------------------------------
# regime / structure (uses levels.json fields added by levels.py)
# ---------------------------------------------------------------------------
def classify_regime(lv, win=None, spread=None, h4=None, h1=None, **kwargs):
    """Backward-compatible wrapper around regime.classify (4 states)."""
    from regime import classify
    return classify(lv, win=win, spread=spread, h4=h4, h1=h1, **kwargs)

def fmt_hl(block, nd=2):
    if not block or block.get("high") is None: return "در دسترس نیست"
    def n(x):
        s = f"{float(x):.{nd}f}".rstrip("0").rstrip(".")
        return s
    extra = " (ناقص)" if block.get("incomplete") else ""
    return f"{n(block['high'])} / {n(block['low'])}{extra}"

def fa_lines(doc, lv=None, win=None, regime=None):
    """Short Persian lines for the brief (no strength words)."""
    lines = []
    if lv:
        st = lv.get("structure") or {}
        ses = lv.get("sessions") or {}
        adr = st.get("adr"); used = st.get("adr_used_pct"); tr = st.get("today_range")
        n = st.get("adr_n") or 14
        regime = regime or classify_regime(lv, win)
        adr_s = f"ADR({n}) حدود {adr:.0f} دلار" if adr else "ADR در دسترس نیست"
        used_s = f"امروز {tr:.1f} دلار ({used:.0f}٪ مصرف‌شده)" if (tr is not None and used is not None) else "دامنه امروز در دسترس نیست"
        lines.append(f"**رژیم:** {regime['fa']} — {regime['why']} · {adr_s} · {used_s}")
        ors = lv.get("opening_ranges") or {}
        if regime and regime.get("allowed_engine_fa"):
            lines[-1] = lines[-1] + f" · موتور مجاز: {regime['allowed_engine_fa']}"
        lines.append("**سقف/کف مرجع:** دیروز " + fmt_hl(ses.get("prev_day"))
                     + " · هفته " + fmt_hl(st.get("week"))
                     + " · هفته قبل " + fmt_hl(st.get("prev_week"))
                     + " · ماه قبل " + fmt_hl(st.get("prev_month"))
                     + " · آسیا " + fmt_hl(ses.get("asia"))
                     + " · لندن " + fmt_hl(ses.get("london"))
                     + " · نیویورک " + fmt_hl(ses.get("ny"))
                     + " · رنج بازگشایی لندن " + fmt_hl(ors.get("london"))
                     + " · رنج بازگشایی نیویورک " + fmt_hl(ors.get("ny")))
    # macro
    if not doc or (not doc.get("ok") and not doc.get("from_cache")):
        lines.append("**ماکرو:** در دسترس نیست")
        return lines
    bits = []
    dxy = doc.get("dxy") or {}
    if dxy.get("unavailable") or dxy.get("last") is None:
        bits.append("DXY در دسترس نیست")
    else:
        last = dxy["last"]; chg = dxy.get("change"); pct = dxy.get("change_pct")
        when = dxy.get("as_of_tehran") or ""
        name = "DXY" if not dxy.get("proxy") else dxy.get("kind", "DXY")
        if chg is None:
            move = ""
        else:
            sign = "+" if chg > 0 else ""
            move = f" ({sign}{chg:.2f}" + (f" / {sign}{pct:.2f}٪" if pct is not None else "") + " امروز)"
        src = f"، {dxy.get('source','')} {when}".strip(" ،") if when else ""
        bits.append(f"{name} {last:g}{move}{('، ' + when + ' تهران') if when else ''}")
        if dxy.get("note"): bits.append(dxy["note"])
    def yld(block, title):
        if not block or block.get("unavailable") or block.get("last") is None:
            return f"{title} در دسترس نیست"
        lag = "، با تأخیر" if block.get("lagged") else ""
        when = block.get("as_of_date") or block.get("as_of_tehran") or ""
        chg = block.get("change")
        move = ""
        if chg is not None:
            sign = "+" if chg > 0 else ""
            move = f" ({sign}{chg:.2f})"
        return f"{title} {block['last']:.2f}٪{move} ({when}{lag})".replace("()", "").replace("(،", "(")
    bits.append(yld(doc.get("us2y"), "بازده ۲ساله"))
    us2y = doc.get("us2y") or {}
    if us2y.get("note") and not us2y.get("unavailable"):
        # keep the note short and attached only once in the brief
        bits.append(us2y["note"])
    if us2y.get("official_fred") and us2y["official_fred"].get("last") is not None:
        bits.append(yld(us2y["official_fred"], "نقدی ۲ساله FRED"))
    bits.append(yld(doc.get("us10y"), "بازده اسمی ۱۰ساله"))
    bits.append(yld(doc.get("real10y"), "بازده واقعی ۱۰ساله"))
    bits.append(yld(doc.get("be5"), "سربه‌سر ۵ساله"))
    bits.append(yld(doc.get("be10"), "سربه‌سر ۱۰ساله"))
    lean = (doc.get("gold_lean") or {}).get("fa") or "در دسترس نیست"
    stale = " · کش کهنه" if doc.get("stale") else ""
    lines.append("**ماکرو:** " + " · ".join(bits) + f" · سوگیری برای طلا: {lean}{stale}")
    return lines

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--ttl", type=int, default=TTL)
    a = ap.parse_args()
    if a.no_fetch:
        doc = _read_cache() or {"ok": False, "dxy": {"unavailable": True}, "us10y": {"unavailable": True},
                                "us2y": {"unavailable": True}, "real10y": {"unavailable": True},
                                "be5": {"unavailable": True}, "be10": {"unavailable": True},
                                "gold_lean": {"fa": "در دسترس نیست"}}
        if doc and doc.get("fetched_at_unix") and _age_s(doc) > a.ttl:
            doc["stale"] = True
    else:
        doc = fetch(force=False, ttl=a.ttl)
    print(json.dumps(doc, ensure_ascii=False, indent=1, default=str))
    for line in fa_lines(doc):
        print(line)

if __name__ == "__main__":
    main()
