# Deploying SuperPredicto to DigitalOcean App Platform

The app spec is [`app.yaml`](app.yaml). The headline feature is the **PRE_DEPLOY
`migrate` job**: it runs `flask db upgrade` against the database after the build
but **before** the new web release receives traffic. So a schema change always
lands in the DB before the code that depends on it serves a request — the
"`column ... does not exist`" sitewide outage becomes structurally impossible.

## Components
- **web** — gunicorn serving `wsgi:app` on `$PORT` (binds 8080). `$5/mo` basic-xxs.
- **migrate** (`kind: PRE_DEPLOY`) — `flask db upgrade`. Runs on every deploy;
  idempotent (no-op when already at head).

Both build from the **repo root** (not `server/`) so the sibling `client/`
templates+static ship with the app; the root `requirements.txt` shim points the
Python buildpack at `server/requirements.txt`.

## First-time setup
1. Install + auth: `doctl auth init`.
2. Create the app from the spec:
   ```bash
   doctl apps create --spec .do/app.yaml
   ```
3. Set the **secret** env vars (App → Settings → Environment Variables, or via
   `doctl apps update <app-id> --spec ...`). Real values, never committed:
   - `SUPABASE_URL` — full Postgres connection string (the Supabase pooler URL)
   - `SECRET_KEY`, `SECURITY_PASSWORD_SALT`
   - `FOOTBALL_DATA_API_KEY`, `INTERNAL_SYNC_TOKEN`
   - `MAILEROO_API_KEY`
   - `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`
4. Set `region` in `app.yaml` to match your Supabase region (lower DB latency),
   then redeploy.

## Deploys after that
`deploy_on_push: true` redeploys on every push to `main`. Each deploy: build →
**migrate (PRE_DEPLOY)** → roll the web service. If the migration fails, the new
release is **not** promoted — the old version keeps serving.

## Not handled here (on purpose)
- **Live-score sync cron** lives in [`infra/do-functions/`](../infra/do-functions/),
  a separate DO Functions scheduled trigger. Keeping it out of the web app means
  the schedule survives web restarts/redeploys.
- **Migrations are forward-only here.** Big/destructive schema changes still need
  the manual expand → migrate → deploy → contract care; this job just guarantees
  the "upgrade" step runs before the new code.
