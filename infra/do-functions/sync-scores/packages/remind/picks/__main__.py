"""Scheduled DO Function: trigger the "make your pick, kickoff soon" reminder.

POSTs to {APP_URL}/internal/remind-picks with the X-Sync-Token header. The app
emails paid+active participants who haven't predicted a game kicking off within
the next 2 hours, at most once per (user, game). Gated to the tournament window
(same as the score sync). Uses only the stdlib (no build step / requirements.txt).
"""
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

# Tournament window (UTC). Start 4h before first kickoff (covers the 2h-before
# reminder for the opening game); stop one week after the final.
SYNC_WINDOW_START = datetime(2026, 6, 11, 15, 0, 0, tzinfo=timezone.utc)
SYNC_WINDOW_END = datetime(2026, 7, 26, 19, 0, 0, tzinfo=timezone.utc)


def main(args):
    now = datetime.now(timezone.utc)
    if now < SYNC_WINDOW_START:
        return {"statusCode": 200, "body": f"skipped: before sync window ({SYNC_WINDOW_START.isoformat()})"}
    if now > SYNC_WINDOW_END:
        return {"statusCode": 200, "body": f"skipped: after sync window ({SYNC_WINDOW_END.isoformat()})"}

    app_url = (os.environ.get("APP_URL") or "").rstrip("/")
    token = os.environ.get("SYNC_TOKEN") or ""
    if not app_url or not token:
        return {"statusCode": 500, "body": "APP_URL or SYNC_TOKEN not configured"}

    req = urllib.request.Request(
        f"{app_url}/internal/remind-picks",
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
