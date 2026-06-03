"""Scheduled DO Function: trigger the "pay your entry" reminder.

POSTs to {APP_URL}/internal/remind-payments with the X-Sync-Token header. The app
emails activated-but-unpaid participants the bank-transfer details (~3 days before
first kickoff), once each. Loosely gated to the pre-tournament days here; the app
enforces the exact [first_kickoff - 3d, first_kickoff) window + per-user dedupe.
Uses only the stdlib (no build step / requirements.txt).
"""
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

# Loose gate around the 3-days-before mark (first game 2026-06-11 19:00Z, so the
# app's real window opens 2026-06-08 19:00Z). The app does the exact timing/dedupe.
PAYMENT_WINDOW_START = datetime(2026, 6, 7, 0, 0, 0, tzinfo=timezone.utc)
PAYMENT_WINDOW_END = datetime(2026, 6, 11, 19, 0, 0, tzinfo=timezone.utc)


def main(args):
    now = datetime.now(timezone.utc)
    if now < PAYMENT_WINDOW_START:
        return {"statusCode": 200, "body": f"skipped: before payment window ({PAYMENT_WINDOW_START.isoformat()})"}
    if now > PAYMENT_WINDOW_END:
        return {"statusCode": 200, "body": f"skipped: after payment window ({PAYMENT_WINDOW_END.isoformat()})"}

    app_url = (os.environ.get("APP_URL") or "").rstrip("/")
    token = os.environ.get("SYNC_TOKEN") or ""
    if not app_url or not token:
        return {"statusCode": 500, "body": "APP_URL or SYNC_TOKEN not configured"}

    req = urllib.request.Request(
        f"{app_url}/internal/remind-payments",
        method="POST",
        headers={"X-Sync-Token": token},
    )
    try:
        with urllib.request.urlopen(req, timeout=55) as resp:
            return {"statusCode": resp.status, "body": resp.read().decode()}
    except urllib.error.HTTPError as e:
        return {"statusCode": e.code, "body": e.read().decode(errors="replace")}
    except Exception as e:  # network / timeout
        return {"statusCode": 502, "body": str(e)}
