"""Bounded, parameterized, read-only financial warehouse queries.

All SUMs are over the latest observation PER CREDIT. Balance differences are
never described as actual cash movements. Monetary Decimal values remain strings.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

L = """WITH latest AS (
 SELECT DISTINCT ON (credit_id) * FROM fw_analytics.fct_credit_period
 ORDER BY credit_id, end_of_period DESC, credit_snapshot_id DESC
)"""


def json_safe(v: Any) -> Any:
    if isinstance(v, Decimal):
        return format(v, "f")
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, dict):
        return {k: json_safe(x) for k, x in v.items()}
    if isinstance(v, (tuple, list)):
        return [json_safe(x) for x in v]
    return v


def rows(conn: Connection, sql: str, **params: Any) -> list[dict[str, Any]]:
    return [json_safe(dict(row)) for row in conn.execute(text(sql), params).mappings().all()]


def one(conn: Connection, sql: str, **params: Any) -> dict[str, Any] | None:
    row = conn.execute(text(sql), params).mappings().one_or_none()
    return json_safe(dict(row)) if row is not None else None


def portfolio(conn: Connection) -> dict[str, Any]:
    return one(conn, L + """
SELECT COUNT(*)::int AS credits, COUNT(DISTINCT project_pk)::int AS projects,
 COUNT(DISTINCT country_id)::int AS countries,
 MIN(end_of_period) AS earliest_latest_period, MAX(end_of_period) AS latest_period,
 SUM(original_principal_amount_usd) AS original_principal_usd,
 SUM(disbursed_amount_usd) AS reported_disbursed_usd,
 SUM(undisbursed_amount_usd) AS reported_undisbursed_usd,
 SUM(cancelled_amount_usd) AS reported_cancelled_usd
FROM latest""") or {}


def countries(conn: Connection, q: str, limit: int, offset: int) -> list[dict[str, Any]]:
    return rows(conn, L + """
SELECT d.country_id, d.country_code, d.country_name, d.region_name,
 COUNT(l.credit_id)::int AS credits,
 SUM(l.original_principal_amount_usd) AS original_principal_usd,
 SUM(l.disbursed_amount_usd) AS reported_disbursed_usd
FROM fw_analytics.dim_country d
LEFT JOIN latest l ON l.country_id=d.country_id
WHERE (:q='' OR d.country_name ILIKE '%'||:q||'%' OR d.country_code ILIKE '%'||:q||'%')
GROUP BY d.country_id,d.country_code,d.country_name,d.region_name
ORDER BY d.country_name, d.country_id LIMIT :limit OFFSET :offset""", q=q, limit=limit, offset=offset)


def projects(conn: Connection, q: str, country_id: int | None, limit: int, offset: int) -> list[dict[str, Any]]:
    return rows(conn, L + """
SELECT p.project_pk, p.project_id, p.project_name, p.country_id, d.country_name,
 COUNT(l.credit_id)::int AS credits, SUM(l.disbursed_amount_usd) AS reported_disbursed_usd
FROM fw_analytics.dim_project p
JOIN fw_analytics.dim_country d ON d.country_id=p.country_id
LEFT JOIN latest l ON l.project_pk=p.project_pk
WHERE (CAST(:country_id AS bigint) IS NULL OR p.country_id=:country_id)
  AND (:q='' OR p.project_id ILIKE '%'||:q||'%' OR COALESCE(p.project_name,'') ILIKE '%'||:q||'%')
GROUP BY p.project_pk,p.project_id,p.project_name,p.country_id,d.country_name
ORDER BY p.project_id LIMIT :limit OFFSET :offset""", country_id=country_id, q=q, limit=limit, offset=offset)


def credits(conn: Connection, q: str, project_pk: int | None, limit: int, offset: int) -> list[dict[str, Any]]:
    return rows(conn, L + """
SELECT c.credit_id,c.credit_number,c.project_pk,p.project_id,p.project_name,
 d.country_name,l.end_of_period AS latest_period,l.credit_status,
 l.disbursed_amount_usd AS reported_disbursed_usd,
 l.undisbursed_amount_usd AS reported_undisbursed_usd
FROM fw_analytics.dim_credit c
JOIN fw_analytics.dim_project p ON p.project_pk=c.project_pk
JOIN fw_analytics.dim_country d ON d.country_id=p.country_id
LEFT JOIN latest l ON l.credit_id=c.credit_id
WHERE (CAST(:project_pk AS bigint) IS NULL OR c.project_pk=:project_pk)
 AND (:q='' OR c.credit_number ILIKE '%'||:q||'%')
ORDER BY c.credit_number LIMIT :limit OFFSET :offset""", project_pk=project_pk, q=q, limit=limit, offset=offset)


def timeline(conn: Connection, credit_id: int, limit: int) -> list[dict[str, Any]]:
    return rows(conn, """
SELECT credit_snapshot_id,credit_id,credit_number,end_of_period,previous_period,
 is_consecutive_month,original_principal_amount_usd,cancelled_amount_usd,
 disbursed_amount_usd,undisbursed_amount_usd,repaid_to_ida_usd,due_to_ida_usd,
 borrowers_obligation_usd,credits_held_usd,exchange_adjustment_usd,
 change_in_reported_disbursed_usd,change_in_reported_undisbursed_usd,
 change_in_reported_repaid_to_ida_usd,ingestion_run_id,source_checksum,source_record_key
FROM fw_analytics.mart_credit_period_metrics
WHERE credit_id=:credit_id ORDER BY end_of_period DESC LIMIT :limit""", credit_id=credit_id,limit=limit)


def lineage(conn: Connection, credit_id: int, period: date) -> dict[str, Any] | None:
    return one(conn, """
SELECT f.credit_id,f.credit_number,f.credit_snapshot_id,f.end_of_period,
 f.ingestion_run_id,f.source_checksum,f.source_record_key,f.created_at
FROM fw_analytics.fct_credit_period f
WHERE f.credit_id=:credit_id AND f.end_of_period=:period""", credit_id=credit_id,period=period)


def watchlist(conn: Connection, limit: int) -> list[dict[str, Any]]:
    # No prediction is implied; flags show descriptive evidence only.
    return rows(conn, """
WITH signals AS (
 SELECT credit_id,credit_number,
 MAX(end_of_period) AS latest_period,
 COUNT(*) FILTER (WHERE previous_period IS NOT NULL AND NOT is_consecutive_month)::int AS reporting_gaps,
 COUNT(*) FILTER (WHERE is_consecutive_month AND change_in_reported_disbursed_usd = 0)::int AS unchanged_consecutive_periods,
 COUNT(*) FILTER (WHERE is_consecutive_month AND change_in_reported_disbursed_usd < 0)::int AS negative_balance_changes
 FROM fw_analytics.mart_credit_period_metrics GROUP BY credit_id,credit_number
)
SELECT * FROM signals
WHERE reporting_gaps > 0 OR unchanged_consecutive_periods > 0 OR negative_balance_changes > 0
ORDER BY reporting_gaps DESC, negative_balance_changes DESC, unchanged_consecutive_periods DESC,credit_id
LIMIT :limit""", limit=limit)
