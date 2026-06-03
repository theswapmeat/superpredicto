"""Scheduled DO Function: hourly reminder tick (signups + payments).

Merged into one function/trigger to stay within DigitalOcean's per-namespace
scheduled-trigger limit. POSTs to BOTH {APP_URL}/internal/remind-signups and
/internal/remind-payments with the X-Sync-Token header. Each endpoint is
window-gated and idempotent in the app (one email per user, only in its own
window), so a single hourly call drives both safely. Stdlib only.
"""
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

# Loose gate covering both reminder windows (payment opens first_kickoff-3d on
# 2026-06-08 19:00Z, signup first_kickoff-1d). The app enforces the exact windows.
WINDOW_START = datetime(2026, 6, 7, 0, 0, 0, tzinfo=timezone.utc)
WINDOW_END = datetime(2026, 6, 11, 19, 0, 0, tzinfo=timezone.utc)
PATHS = ["/internal/remind-signups", "/internal/remind-payments"]


def _post(app_url, token, path):
    req = urllib.request.Request(
        app_url + path, method="POST", headers={"X-Sync-Token": token}
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return {"path": path, "statusCode": resp.status, "body": resp.read().decode()}
    except urllib.error.HTTPError as e:
        return {"path": path, "statusCode": e.code, "body": e.read().decode(errors="replace")}
    except Exception as e:  # network / timeout
        return {"path": path, "statusCode": 502, "body": str(e)}


def main(args):
    now = datetime.now(timezone.utc)
    if now < WINDOW_START:
        return {"statusCode": 200, "body": f"skipped: before reminder window ({WINDOW_START.isoformat()})"}
    if now > WINDOW_END:
        return {"statusCode": 200, "body": f"skipped: after reminder window ({WINDOW_END.isoformat()})"}

    app_url = (os.environ.get("APP_URL") or "").rstrip("/")
    token = os.environ.get("SYNC_TOKEN") or ""
    if not app_url or not token:
        return {"statusCode": 500, "body": "APP_URL or SYNC_TOKEN not configured"}

    results = [_post(app_url, token, p) for p in PATHS]
    return {"statusCode": 200, "body": json.dumps(results)}
