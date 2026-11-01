# FlowWatch V7 Day 2 — Financial API contracts

Data source: `flowwatch_historical_gate.fw_analytics`. **No write endpoints.**
The API requires a dedicated `flowwatch_api_reader` PostgreSQL login and
starts each transaction using `SET TRANSACTION READ ONLY`. API startup fails
without a >=32-character JWT secret, a dedicated reader password, and an
Argon2-hashed local identity file. No plaintext passwords are tracked.

## Authentication

`POST /api/v1/auth/token` accepts JSON `username` and `password`; returns an
HS256 signed access token valid for 30 minutes. JWT audience and issuer are
verified. `GET /api/v1/auth/me` returns the active role. Local users have
`analyst`, `operator`, or `administrator` roles. **Current API routes are all
read-only**, so analyst access is sufficient; operator/admin write actions
are not implemented. Pilot auth is not an external OIDC integration.

## Queries

| GET endpoint | Semantics |
| --- | --- |
| `/api/v1/health/live` | Process responds, public |
| `/api/v1/health/ready` | Checks isolated DB and five dbt relations, authenticated |
| `/api/v1/operations/warehouse` | Operator or administrator only; warehouse readiness metadata |
| `/api/v1/portfolio/summary` | Last available snapshot PER credit; balances not cash flows |
| `/api/v1/countries?q=&limit=&offset=` | Countries and bounded latest-credit aggregates |
| `/api/v1/projects?q=&country_id=&limit=&offset=` | Project list, optionally scoped to country |
| `/api/v1/credits?q=&project_pk=&limit=&offset=` | Credit list, optionally scoped to project |
| `/api/v1/credits/{credit_id}/timeline?limit=` | Descending observed periods and adjacent-month balance changes |
| `/api/v1/credits/{credit_id}/lineage?period=YYYY-MM-DD` | Canonical snapshot locator and source run/checksum/key |
| `/api/v1/risk/watchlist?limit=` | Rule-derived gaps and balance changes, **not ML predictions** |

`q` is bound as an SQL parameter. Limit ≤100 for directories/watchlist; timeline
≤500; no unbounded queries. Each decimal field is serialized as an exact
**string**, not a floating-point JSON number. Lineage identifies the canonical
source observation, not a fully independent MongoDB verification.

There is no validated as-of date alignment across all credits: summary uses
latest-observation-per-credit and displays minimum/maximum latest dates.
Counts of unchanged financial balances are **descriptive**; do not interpret
them as confirmed risk labels. Month-to-month differences are undefined across
missing periods, not imputed to zero.

## Not yet implemented

Full external OIDC federation, distributed rate limiting, database-backed
user governance, risk prediction, horizon forecasting, evidence trails across
raw Mongo records, service metrics, end-to-end browser tests, and production
hardening are reserved for later work. The local login limiter is in-process
and is not distributed across multiple Uvicorn workers. This package is a
bounded internal pilot, not an exposed production deployment.
