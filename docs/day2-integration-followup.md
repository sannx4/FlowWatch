# FlowWatch V7 — Day 2 Integration Follow-up

This patch corrects a **frontend selection-scope bug** observed during interactive
Day 2 testing: a credit opened from the Risk Watchlist could retain a previous
project filter. The directory then showed credits from an older project while
the history showed the risk-selected credit.

## Changes

- Clear credit history and provenance when changing country/project/credit-search scope.
- Clear the previous project filter when opening a credit from the Risk Watchlist.
- Reject stale asynchronous timeline, provenance, and directory-list responses.
- Add a **localhost-only**, read-only API smoke test that prompts for the local
  analyst password without echoing it or logging the JWT.
- Include offline tests for the smoke test's safety behavior.

## Windows commands

Extract the patch ZIP into `E:\flowwatch\FlowWatch` after stopping the local Vite
server (optional; Vite hot reload is supported). This overlay **replaces only**
`frontend/src/App.tsx` and adds the smoke script, its tests and this document.
It does not modify Day 1 or `day2_local/` credentials.

From CMD:

```bat
cd /d E:\flowwatch\FlowWatch
.venv\Scripts\activate
python -m ruff check src tests scripts
python -m pytest -q
cd frontend
npm run build
cd ..
```

Start FastAPI in a separate terminal if not already running:

```bat
python -m uvicorn src.api.day2.app:app --host 127.0.0.1 --port 8000
```

In another terminal, **without pasting any password into the command line**:

```bat
python -m scripts.day2_live_smoke --username analyst
```

Enter the local analyst password when prompted. Expected successful line:

`PASS_DAY2_LOCAL_API_ACCEPTANCE`

The smoke probe sends no database writes; the only POST is the local login
endpoint. It tests unauthenticated denial, JWT identity, operator access
denial, invalid bounds, warehouse readiness, summary and directories, a credit
history, and source lineage. It **does not replace** a browser E2E test or
full PostgreSQL read-permission audit.

## Browser regression

1. In Country & Project Explorer select India, then project P009616. Click
   IDA00210 and confirm the history shows **Credit #665** and 166 observations.
2. In Risk Watchlist click IDA00910. Credit Intelligence should show the
   correct credit's history, **without** the old `Clear project 665` filter.
3. Select another project: the old credit history and lineage should disappear
   until a credit from the new project is selected.
4. Quickly select two different credits: the later selection must win even if
   the earlier HTTP response arrives later.

The 3,000-observation historical sample is bounded, so the live smoke verifies
its current content only. It does not establish full World Bank coverage or
forecasting readiness.
