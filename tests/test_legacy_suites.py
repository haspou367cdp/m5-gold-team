"""Run the existing bot and Edge Function suites so one pytest command covers everything."""
import os, shutil, subprocess, sys, tempfile
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_bot_suite():
    env = dict(os.environ, STATE_DIR=tempfile.mkdtemp())
    p = subprocess.run([sys.executable, "bot/test_bot.py"], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
    assert p.returncode == 0 and p.stdout.strip().endswith("0 failed"), p.stdout[-2000:]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_edge_function_suite():
    p = subprocess.run(["node", "test.mjs"], cwd=os.path.join(ROOT, "supabase/functions/tg-bot"),
                       capture_output=True, text=True, timeout=300)
    assert p.returncode == 0 and p.stdout.strip().endswith("0 failed"), p.stdout[-2000:]


@pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
def test_assistant_suite():
    p = subprocess.run(["node", "test_assist.mjs"], cwd=os.path.join(ROOT, "supabase/functions/tg-bot"),
                       capture_output=True, text=True, timeout=300)
    assert p.returncode == 0 and p.stdout.strip().endswith("0 failed"), p.stdout[-2000:]
