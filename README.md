# PWYS Communications Dashboard

A small internal dashboard for Play Where You Stay (Memphis youth soccer nonprofit) to
track SMS and email communications sent to parents, and reply/open rates, alongside a
secure login for PWYS staff and Rev Up With AI.

This complements the existing Make.com registration → SMS/email automation (see
`docs/MAKE_COM_INTEGRATION.md`) — it does not replace or modify that scenario. Make.com
POSTs an event here every time an SMS is sent/received or an email is sent/opened/clicked;
this app stores that history and renders it.

## Stack

- **Backend/frontend:** FastAPI + Jinja2 server-rendered templates (no JS build step)
- **Database:** PostgreSQL in production, SQLite for local dev (via `DATABASE_URL`)
- **Auth:** Email/password with server-side sessions (bcrypt-hashed passwords)
- **Charts:** Chart.js via CDN

## Local development

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

copy .env.example .env          # then edit SESSION_SECRET / INGEST_API_KEY
python scripts/create_user.py "you@example.com" "Your Name" --admin
python scripts/seed_demo_data.py   # optional: fake data so the dashboard isn't empty

uvicorn app.main:app --reload
```

Visit http://127.0.0.1:8000 and log in with the account you created.

## Project structure

```
app/
  main.py           routes: login, dashboard, account/password
  auth.py           session handling, password hashing
  database.py       SQLAlchemy engine/session (Postgres/SQLite)
  models.py         User, SmsEvent, EmailEvent
  metrics.py        aggregation: send counts, reply/open rates, timeseries
  ingest.py         POST /api/ingest/sms and /api/ingest/email (called by Make.com)
  schemas.py        pydantic request bodies for the ingest endpoints
  templates/        Jinja2 HTML
scripts/
  create_user.py    create/reset a login (also used to onboard Keith/PWYS staff)
  seed_demo_data.py dev-only fake data generator
docs/
  MAKE_COM_INTEGRATION.md   exact Make.com HTTP module config to add
  DEPLOYMENT.md             hosting + GoDaddy DNS + first-deploy steps
```

## Status

- [x] Core app: auth, dashboard, ingest API, metrics
- [ ] Deployed to production host
- [ ] `dashboard.revupwithai.com` DNS pointed at it (GoDaddy)
- [ ] Make.com scenario updated to POST SMS events (see docs/MAKE_COM_INTEGRATION.md)
- [ ] Robly email logging wired in — **blocked on Keith delivering Robly API
      credentials**, per the PWYS automation handoff. The dashboard already supports
      email metrics; it'll just show zero email data until that's connected.
- [ ] PWYS staff accounts created (need emails from Keith)
