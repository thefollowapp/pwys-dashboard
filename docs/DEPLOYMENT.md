# Deploying the PWYS dashboard

**Status: done.** Live at `https://pwys.revupwithai.com`, hosted on Railway
(project `pwys-dashboard`) with a Postgres addon. The steps below are kept as
reference for redeploying, onboarding another environment, or recovering access.

## 1. Host the app + database

Recommended: **Railway** (or Render) — both auto-detect the `Procfile`, support Postgres
as an addon, and are cheap enough for a pro bono nonprofit project (Railway's Hobby plan
or Render's Starter tier, a few dollars/month).

1. Push this repo to GitHub.
2. Create a new Railway/Render project from the repo.
3. Add a Postgres database addon — copy its connection string into the app's
   `DATABASE_URL` environment variable. Railway/Render give you a string starting
   `postgresql://` or `postgres://` — change that prefix to `postgresql+psycopg://`
   (this app uses the psycopg3 driver).
4. Set the remaining environment variables (see `.env.example`):
   - `SESSION_SECRET` — `python -c "import secrets; print(secrets.token_hex(32))"`
   - `INGEST_API_KEY` — `python -c "import secrets; print(secrets.token_urlsafe(32))"`
   - `ENV=production`
5. Deploy. The platform will run `uvicorn app.main:app --host 0.0.0.0 --port $PORT` per
   the Procfile.

## 2. Point the subdomain at it (GoDaddy DNS)

Railway/Render will give you a generated domain (e.g. `pwys-dashboard.up.railway.app`)
and a "custom domain" option that gives you a CNAME target.

In GoDaddy's DNS management for `revupwithai.com`, add:

| Type  | Name (host) | Value                          |
|-------|-------------|---------------------------------|
| CNAME | dashboard   | `<value provided by Railway/Render>` |

That makes the dashboard live at `dashboard.revupwithai.com`. (Swap `dashboard` for
whatever subdomain you prefer, e.g. `pwys`.) DNS propagation can take up to an hour;
Railway/Render will auto-provision an SSL certificate once the CNAME resolves.

## 3. Create the first accounts

After the first deploy, run once (via the platform's shell/console, or locally pointed
at the production `DATABASE_URL`):

```bash
python scripts/create_user.py "ryates051@gmail.com" "Robby" --admin
```

Repeat for Keith and any other PWYS staff once you have their emails — see
`scripts/create_user.py --help`.

## 4. Wire up Make.com

Follow `docs/MAKE_COM_INTEGRATION.md` to add the two logging HTTP modules to the
existing Make.com scenario, using the production `INGEST_API_KEY`.
