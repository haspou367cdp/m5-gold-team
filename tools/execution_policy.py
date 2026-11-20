"""No-execution boundary. This system only analyses and sends signals; the owner places every trade by hand.

tests/test_no_execution.py scans the repo (Python + the Supabase Edge Function) and fails if any
order-submission, DaryaGold login or browser-automation path appears. Never flip these constants.
"""
EXECUTION_MODE = "MANUAL_SIGNAL_ONLY"
AUTOMATED_ORDER_EXECUTION = False
BROKER_LOGIN_ENABLED = False
BROWSER_AUTOMATION_ENABLED = False
AUTO_CLOSE_POSITIONS = False          # the 00:30 close only sends a reminder; never closes anything
STORE_BROKER_CREDENTIALS = False


def assert_manual_only():
    """Raise if the policy was changed. Called by the risk gate before every decision."""
    if (EXECUTION_MODE != "MANUAL_SIGNAL_ONLY" or AUTOMATED_ORDER_EXECUTION or BROKER_LOGIN_ENABLED
            or BROWSER_AUTOMATION_ENABLED or AUTO_CLOSE_POSITIONS or STORE_BROKER_CREDENTIALS):
        raise RuntimeError("execution policy violated: this system is MANUAL_SIGNAL_ONLY")
    return True
