"""Scheduled DO Function: trigger the "finish signing up" reminder.

POSTs to {APP_URL}/internal/remind-signups with the X-Sync-Token header. The app
sends a one-off "24h to kickoff, finish signing up" email to each invited-but-
never-activated participant — only inside the precise 24h pre-kickoff window (the
app computes first kickoff from the DB) and only once per user.

This function is loosely gated to the days before the tournament so it isn't
calling the app hourly year-round; the app does the exact timing + dedupe.
Uses only the stdlib (no build step / requirements.txt).
"""
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

# Loose gate: the days leading up to the first game (2026-06-11 19:00Z). The app
# narrows this to exactly [first_kickoff - 24h, first_kickoff) and sends once/user.
SIGNUP_WINDOW_START = datetime(2026, 6, 9, 0, 0, 0, tzinfo=timezone.utc)
SIGNUP_WINDOW_END = datetime(2026, 6, 11, 19, 0, 0, tzinfo=timezone.utc)


def main(args):
    now = datetime.now(timezone.utc)
    if now < SIGNUP_WINDOW_START:
        return {"statusCode": 200, "body": f"skipped: before signup window ({SIGNUP_WINDOW_START.isoformat()})"}
    if now > SIGNUP_WINDOW_END:
        return {"statusCode": 200, "body": f"skipped: after signup window ({SIGNUP_WINDOW_END.isoformat()})"}

    app_url = (os.environ.get("APP_URL") or "").rstrip("/")
    token = os.environ.get("SYNC_TOKEN") or ""
    if not app_url or not token:
        return {"statusCode": 500, "body": "APP_URL or SYNC_TOKEN not configured"}

    req = urllib.request.Request(
        f"{app_url}/internal/remind-signups",
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
