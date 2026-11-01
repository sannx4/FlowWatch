# FlowWatch V7 — Day 2 Financial Intelligence Application

This ZIP is a **new-file overlay** for the merged `main` branch after PR #25.
It adds a read-only FastAPI backend and a React/TypeScript analyst workspace.
It does not modify Day 1 dbt, ingestion, existing migrations, or GitHub Actions.

## Included

- Exact-decimal finance API with portfolio, country, project, credit, timeline,
  source locator, and descriptive risk-watchlist endpoints.
- Signed 30-minute JWT for local pilot identities (Argon2 hashes).
- Separate least-privilege PostgreSQL reader; every DB transaction is read-only.
- CORS locked to the local React origin; API bound to localhost in instructions.
- React workspace with 4 working data-driven analytical screens, login, and
  explicit placeholders for later forecasting/operations modules.
- Offline API contract/unit tests.

## Windows CMD setup

Run these commands from `E:\flowwatch\FlowWatch`, after `git switch main` and
`git pull --ff-only origin main`. Create a feature branch first:

```bat
git switch -c v7-day2-financial-intelligence
```

Download the ZIP file, then extract at repository root (change ZIP path if needed):

```bat
powershell -NoProfile -Command "Expand-Archive -LiteralPath 'C:\Users\ADMIN\Downloads\FlowWatch_V7_Day2_Financial_Intelligence.zip' -DestinationPath 'E:\flowwatch\FlowWatch' -Force"
```

Install the API into `.venv`:

```bat
python -m pip install -r requirements-api.txt
python -m pytest -q tests/unit/test_day2_financial_api.py
```

### Reader role (one-time, explicit DBA operation)

**Do not apply this SQL against the primary `flowwatch` database.**
Connect to the existing isolated `flowwatch_historical_gate` database as
an authorized DBA. Review and run `docs/day2-reader-role.sql`, then use psql:

```sql
\password flowwatch_api_reader
```

`\password` asks interactively; do not put the password in committed SQL.
If the database uses the default Docker port binding, the host endpoint is
`127.0.0.1:5434`; verify it before running commands. No migrations are needed.

### Local auth configuration

From CMD:

```bat
python -m scripts.day2_init_auth --username analyst --role analyst
```

Enter an analyst password (>=12 characters), confirm it, and enter the
**same** PostgreSQL password configured for `flowwatch_api_reader`. This
creates ignored `day2_local/users.json` and `day2_local/.env`. The generator
will not overwrite existing credentials. If the database port differs from
5434, set `POSTGRES_HOST` / `POSTGRES_PORT` in your root `.env` (or CMD).

**Never commit** `day2_local/` contents. For the internal pilot, configure
OS file access to restrict who can read secrets.

### Start API

```bat
python -m uvicorn src.api.day2.app:app --host 127.0.0.1 --port 8000
```

Check `http://127.0.0.1:8000/docs` and `http://127.0.0.1:8000/api/v1/health/live`.
Swagger authentication requires a bearer token from `/api/v1/auth/token`.

### Start React frontend in a *second* CMD window

```bat
cd /d E:\flowwatch\FlowWatch\frontend
npm install
npm run dev
```

Open `http://localhost:5173`. **Do not deploy publicly.** Node 20+ is
recommended. Vite proxies `/api` to the localhost API.

### Validate

```bat
python -m pytest -q tests/unit/test_day2_financial_api.py
python -m pytest -q
python -m pip check
cd frontend
npm run build
```

After successful end-to-end smoke testing, inspect status and commit only
intended new files. `frontend/node_modules/` and `frontend/dist/` must not be
committed; `frontend/.gitignore` excludes them. The existing untracked
`reports/day39-42-research-gate.json` should remain local.

## Scope / gate status

This package provides a tested **offline starting implementation**, not
verified live database integration. Read-only authentication, API connectivity,
financial reconciliation, frontend build, and end-to-end UX must all be
checked on your Windows environment before the Day 2 completion gate can be
closed. The four working modules require a built Day 1 warehouse. Unlike
claims about ML training readiness, frontend summary amounts are explicitly
latest-per-credit period-end balances. No forecast model is installed.
