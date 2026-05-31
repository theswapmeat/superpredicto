"""Scheduled DO Function: trigger the app's live-score sync.

POSTs to {APP_URL}/internal/sync-scores with the X-Sync-Token header. The app
does the real work (pull football-data.org scores + rerun scoring); this is just
the scheduler's "finger on the button". Uses only the stdlib so the function
needs no build step / requirements.txt.
"""
import os
import urllib.error
import urllib.request


def main(args):
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
