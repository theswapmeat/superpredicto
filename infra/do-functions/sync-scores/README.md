# Live-score sync — DigitalOcean Functions (scheduled)

A serverless cron, native to DigitalOcean, that replaces the old GitHub Actions
workflow. Every 5 minutes a scheduled trigger invokes the `sync/poll` function,
which POSTs to the app's `/internal/sync-scores` endpoint (X-Sync-Token header).
The app pulls live football-data.org scores and reruns scoring.

```
sync-scores/
├── project.yml                    # function + scheduled trigger spec
├── .env.example                   # copy to .env (gitignored) with your values
└── packages/sync/poll/__main__.py # the function (stdlib only, no build step)
```

## One-time setup

```bash
doctl auth init                 # paste a DO API token
doctl serverless install        # installs the serverless plugin
doctl serverless connect        # creates/links a Functions namespace
```

## Configure secrets

```bash
cp .env.example .env            # then edit .env
#   APP_URL    = https://<your-app>.ondigitalocean.app   (no trailing slash)
#   SYNC_TOKEN = <same value as the app's INTERNAL_SYNC_TOKEN>
```

`.env` is gitignored. At deploy, `doctl` substitutes `${APP_URL}` / `${SYNC_TOKEN}`
from it into the function's environment (so the token lives in the function, never
in the repo).

## Deploy

```bash
cd infra/do-functions/sync-scores
doctl serverless deploy .
```

## Verify

```bash
doctl serverless functions invoke sync/poll        # manual run — expect {"ok": true, ...}
doctl serverless triggers list                     # confirm poll-10min is scheduled
doctl serverless activations list                  # recent runs (incl. the scheduled ones)
doctl serverless activations logs <activation-id>  # inspect a run
```

A successful run returns the app's JSON, e.g.
`{"statusCode": 200, "body": "{\"ok\": true, \"tournament\": 2026, \"sync\": {...}}"}`.

## Notes

- **Cost:** one tiny stdlib call every 5 min is far inside the Functions free
  allowance (90k GB-seconds/month).
- **Timezone:** the cron runs in UTC.
- **Change the cadence:** edit `cron` in `project.yml` and redeploy. Tighten it on
  match days (e.g. `*/2 * * * *`) — still well within football-data.org's 10 req/min.
- **Pause it:** `doctl serverless triggers fire`/delete, or just
  `doctl serverless undeploy sync/poll`.
