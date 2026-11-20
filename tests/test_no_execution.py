"""Fails if any order-submission, DaryaGold login or browser-automation path exists in the code."""
import os, re
import execution_policy as EP

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXTS = (".py", ".ts", ".js", ".mjs")
SKIP_DIRS = {".git", "node_modules", "__pycache__", "tests"}
SKIP_FILES = {os.path.join(ROOT, "tools", "execution_policy.py")}
FORBIDDEN = re.compile(
    r"selenium|playwright|puppeteer|pyautogui|webdriver|chromium|headless|"
    r"place_?order|submit_?order|order_?send|create_?order|new_?order|close_?position|"
    r"metatrader|\bmt5\b|ccxt|"
    r"darya\w*\.(ir|com|net)|login|password|\botp\b|sms_?code|captcha", re.I)
ALLOWED_HOSTS = {"api.telegram.org", "api.github.com", "token.actions.githubusercontent.com", "fred.stlouisfed.org",
                 "freeserv.dukascopy.com", "nfs.faireconomy.media", "query1.finance.yahoo.com", "x"}
URL = re.compile(r"https?://([A-Za-z0-9.\-]+)")


def code_files():
    for d, dirs, files in os.walk(ROOT):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for f in files:
            p = os.path.join(d, f)
            if f.endswith(EXTS) and p not in SKIP_FILES:
                yield p


def test_policy_constants():
    assert EP.EXECUTION_MODE == "MANUAL_SIGNAL_ONLY"
    assert EP.AUTOMATED_ORDER_EXECUTION is False and EP.BROKER_LOGIN_ENABLED is False
    assert EP.BROWSER_AUTOMATION_ENABLED is False and EP.AUTO_CLOSE_POSITIONS is False
    assert EP.STORE_BROKER_CREDENTIALS is False and EP.assert_manual_only()


def test_scan_covers_python_and_edge_function():
    files = list(code_files())
    assert any(p.endswith("bot/bot.py") for p in files)
    assert any(p.endswith("supabase/functions/tg-bot/index.ts") for p in files)
    assert any(p.endswith("supabase/functions/tg-bot/lib.js") for p in files)


def test_no_execution_paths():
    hits = []
    for p in code_files():
        for i, line in enumerate(open(p, encoding="utf-8", errors="ignore"), 1):
            if FORBIDDEN.search(line):
                hits.append(f"{os.path.relpath(p, ROOT)}:{i}: {line.strip()[:120]}")
    assert hits == [], "execution / login / browser-automation code found:\n" + "\n".join(hits)


def test_only_known_hosts():
    bad = []
    for p in code_files():
        for h in URL.findall(open(p, encoding="utf-8", errors="ignore").read()):
            if h not in ALLOWED_HOSTS and not h.endswith(".supabase.co"):
                bad.append(f"{os.path.relpath(p, ROOT)}: {h}")
    assert bad == [], "unexpected external host:\n" + "\n".join(bad)


def test_scanner_detects_violations(tmp_path):
    for s in ("from selenium import webdriver", "mt5.order_send(req)", "requests.post('https://daryagold.ir/login')",
              "await page.fill('#password', pw)"):
        assert FORBIDDEN.search(s), s
    assert not FORBIDDEN.search("entry_type = 'order (limit, no spread)'")
