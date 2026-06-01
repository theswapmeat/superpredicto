"""Scheduled DO Function: trigger the app's live-score sync.

POSTs to {APP_URL}/internal/sync-scores with the X-Sync-Token header. The app
does the real work (pull football-data.org scores + rerun scoring); this is just
the scheduler's "finger on the button". Uses only the stdlib so the function
needs no build step / requirements.txt.

The scheduler trigger fires every 5 minutes year-round (5-field cron has no year
field), so the actual polling window is gated here. Polling only matters once the
tournament is under way, so we hard-code the window to [4h before first kickoff,
one week after the last game] in UTC. Starting 4 hours early gives a live smoke
test: if the scheduler isn't firing as expected, there's a buffer to fix it
before the first real match. Calls outside the window are no-ops.
"""
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

# FIFA World Cup 2026 (UTC). First game: 2026-06-11 19:00:00Z.
# Start polling 4h before first kickoff (15:00Z) as a live smoke test / buffer.
# Final: 2026-07-19 19:00:00Z -> stop polling one week later.
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
        f"{app_url}/internal/sync-scores",
        method="POST",
        headers={"X-Sync-Token": token},
    )
    try:
        with urllib.request.urlopen(req, timeout=55) as resp:
            return {"statusCode": resp.status, "body": resp.read().decode()}
    except urllib.error.HTTPError as e:
        # Surface the app's error body (e.g. 403 bad token, 400 no active tournament)
        return {"statusCode": e.code, "body": e.read().decode(errors="replace")}
    except Exception as e:  # network / timeout
        return {"statusCode": 502, "body": str(e)}
