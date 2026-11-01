"""V7 Day39-42: isolated research audit and immutable exact-decimal Parquet export.

Read-only database transaction. No HTTP, no Mongo writes, no migrations.
Audit is default; --export explicitly authorizes *local file* publication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from scripts.day34_38_dbt_gate import (
    DB_NAME,
    ROOT,
    _connection_settings,
    connect_isolated,
    validate_source,
    validate_warehouse,
)
from src.warehouse.research_contracts import (
    FINANCIAL_COLUMNS,
    ResearchContractError,
    coverage_audit,
)

VERSION = "day39-42-research-export-v1"
MAX_ROWS = 10000  # Current validated, bounded implementation; never imply complete history.
OUTPUT_ROOT = ROOT / "artifacts" / "flowwatch_day1"
DEFAULT_REPORT = ROOT / "reports" / "day39-42-research-gate.json"
BASE_COLUMNS = (
    "publication_run_id", "credit_snapshot_id", "credit_id", "credit_number",
    "project_pk", "project_id", "country_id", "country_code", "country_name",
    "region_id", "region_name", "end_of_period", "credit_status",
    "last_disbursement_date", *FINANCIAL_COLUMNS,
    "source_checksum", "source_record_key",
)


def _source_query() -> str:
    fields = ",\n       ".join(f"s.{name}" for name in FINANCIAL_COLUMNS)
    return f"""
        SELECT d.run_id::text AS publication_run_id,
               s.credit_snapshot_id, s.credit_id, c.credit_number,
               p.project_pk, p.project_id, co.country_id, co.country_code, co.country_name,
               r.region_id, r.region_name,
               s.end_of_period, s.credit_status, s.last_disbursement_date,
               {fields},
               s.source_checksum, s.source_record_key,
               d.source_checksum AS decision_checksum,
               d.source_record_key AS decision_key,
               s.ingestion_run_id::text AS snapshot_ingestion_run_id
        FROM public.historical_canonical_decisions d
        JOIN public.credit_snapshots s ON s.credit_snapshot_id = d.credit_snapshot_id
        JOIN public.credits c ON c.credit_id = s.credit_id
        JOIN public.projects p ON p.project_pk = c.project_pk
        JOIN public.countries co ON co.country_id = p.country_id
        JOIN public.regions r ON r.region_id = co.region_id
        WHERE d.run_id = :run_id AND d.outcome <> 'REJECTED'
        ORDER BY c.credit_number, s.end_of_period, s.credit_snapshot_id
    """


def _warehouse_mismatch_query() -> str:
    comparisons = [
        "f.credit_id IS DISTINCT FROM s.credit_id",
        "f.end_of_period IS DISTINCT FROM s.end_of_period",
        "f.credit_number IS DISTINCT FROM c.credit_number",
        "f.project_pk IS DISTINCT FROM p.project_pk",
        "f.country_id IS DISTINCT FROM p.country_id",
        "f.credit_status IS DISTINCT FROM s.credit_status",
        "f.last_disbursement_date IS DISTINCT FROM s.last_disbursement_date",
        *[f"f.{col} IS DISTINCT FROM s.{col}" for col in FINANCIAL_COLUMNS],
        "f.ingestion_run_id IS DISTINCT FROM s.ingestion_run_id",
        "f.source_checksum IS DISTINCT FROM s.source_checksum",
        "f.source_record_key IS DISTINCT FROM s.source_record_key",
    ]
    where = " OR\n                    ".join(comparisons)
    return f"""
        SELECT COUNT(*)
        FROM public.historical_canonical_decisions d
        JOIN public.credit_snapshots s ON s.credit_snapshot_id=d.credit_snapshot_id
        JOIN public.credits c ON c.credit_id=s.credit_id
        JOIN public.projects p ON p.project_pk=c.project_pk
        LEFT JOIN fw_analytics.fct_credit_period f
            ON f.credit_snapshot_id=s.credit_snapshot_id
        WHERE d.run_id=:run_id AND d.outcome <> 'REJECTED'
          AND (f.credit_snapshot_id IS NULL OR {where})
    """


def _read_snapshot(connection: Connection, run_id: UUID) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run all checks in one repeatable-read, read-only PostgreSQL transaction."""
    connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    source = validate_source(connection, run_id)
    warehouse = validate_warehouse(connection, source)
    if int(source["published_rejected"]) != 0:
        raise ResearchContractError("Refusing partial/quarantined publication for this release")
    n = int(source["published_accepted"])
    if n < 1 or n > MAX_ROWS:
        raise ResearchContractError(f"Bounded export requires 1..{MAX_ROWS} accepted rows")
    upstream = connection.execute(text("""
        SELECT observed_total, page_size, status FROM public.historical_backfill_runs
        WHERE run_id=:run_id
    """), {"run_id": run_id}).mappings().one()
    if upstream["status"] != "COMPLETE":
        raise ResearchContractError("Incomplete upstream backfill")
    if source["canonical_snapshot_rows"] != n:
        raise ResearchContractError("Canonical universe differs from this publication; review run isolation")
    if warehouse["fact_count"] != n or warehouse["metric_count"] != n:
        raise ResearchContractError("Expected source/fact/metric equality for bounded publication")
    mismatch = connection.execute(text(_warehouse_mismatch_query()), {"run_id": run_id}).scalar_one()
    if mismatch:
        raise ResearchContractError(f"{mismatch} exact financial/source/fact discrepancies")
    raw_rows = [dict(row) for row in connection.execute(
        text(_source_query()), {"run_id": run_id}
    ).mappings().all()]
    if len(raw_rows) != n:
        raise ResearchContractError(f"Decision/source join yielded {len(raw_rows)} instead of {n}")
    snapshot_ids: set[int] = set()
    source_keys: set[str] = set()
    clean: list[dict[str, Any]] = []
    for row in raw_rows:
        if (row["decision_key"] != row["source_record_key"]
                or row["decision_checksum"] != row["source_checksum"]
                or row["snapshot_ingestion_run_id"] != str(run_id)):
            raise ResearchContractError("Publication lineage mismatch")
        if row["credit_snapshot_id"] in snapshot_ids or row["source_record_key"] in source_keys:
            raise ResearchContractError("Duplicated snapshot or source observation")
        snapshot_ids.add(row["credit_snapshot_id"])
        source_keys.add(row["source_record_key"])
        clean.append({key: row[key] for key in BASE_COLUMNS})
    return clean, {
        "database": DB_NAME, "schema": "fw_analytics", "run_id": str(run_id),
        "published_source_records": int(source["published_observations"]),
        "source_total_reported": int(upstream["observed_total"]),
        "canonical_snapshot_rows": n, "warehouse_fact_rows": int(warehouse["fact_count"]),
        "warehouse_metric_rows": int(warehouse["metric_count"]),
        "complete_source_backfill": False,
        "independent_financial_field_parity": "PASS",
        "publication_lineage": "PASS",
    }


def _serial_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return {"decimal": format(value, "f")}
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (str, int)) or value is None:
        return value
    raise ResearchContractError(f"Unserializable source value {type(value).__name__}")


def canonical_digest(rows: list[dict[str, Any]]) -> str:
    """Domain-separated, order-dependent, type-explicit logical fingerprint."""
    digest = hashlib.sha256(b"flowwatch-v7-day39-42-canonical-v1\n")
    for row in rows:
        token = [_serial_value(row[col]) for col in BASE_COLUMNS]
        digest.update(json.dumps(token, ensure_ascii=True, separators=(",", ":")).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _parquet_schema(pa: Any) -> Any:
    ids = {"credit_snapshot_id", "credit_id", "project_pk", "country_id", "region_id"}
    dates = {"end_of_period", "last_disbursement_date"}
    fields = []
    for column in BASE_COLUMNS:
        if column in ids:
            kind = pa.int64()
        elif column in dates:
            kind = pa.date32()
        elif column == "service_charge_rate":
            kind = pa.decimal128(12, 6)
        elif column in FINANCIAL_COLUMNS:
            kind = pa.decimal128(24, 2)
        else:
            kind = pa.string()
        fields.append(pa.field(column, kind, nullable=True))
    return pa.schema(fields)


def _verify_existing(dest: Path, manifest: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    """Existing version may be reused only after full bytes and logical-row verification."""
    from pyarrow import parquet as pq

    if not dest.is_dir():
        raise ResearchContractError("Expected immutable export directory")
    for name in ("credit_period.parquet", "audit.json", "manifest.json"):
        if not (dest / name).is_file():
            raise ResearchContractError(f"Missing immutable artifact: {name}")
    saved = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
    if saved != manifest:
        raise ResearchContractError("Existing dataset manifest differs from current evidence")
    if sha256_file(dest / "credit_period.parquet") != saved["files"]["credit_period.parquet"]["sha256"]:
        raise ResearchContractError("Existing Parquet checksum mismatch")
    if sha256_file(dest / "audit.json") != saved["files"]["audit.json"]["sha256"]:
        raise ResearchContractError("Existing audit checksum mismatch")
    restored = pq.read_table(dest / "credit_period.parquet").to_pylist()
    if restored != rows:
        raise ResearchContractError("Existing Parquet rows differ from live source snapshot")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")


def publish_parquet(
    rows: list[dict[str, Any]], audit: dict[str, Any],
    provenance: dict[str, Any], digest: str, artifact_root: Path = OUTPUT_ROOT,
) -> dict[str, Any]:
    """Write local content-addressed artifacts; refuse overwrite and validate readback."""
    try:
        import pyarrow as pa
        from pyarrow import parquet as pq
    except ImportError as exc:
        raise ResearchContractError("Install requirements-research.txt (pyarrow) first") from exc
    schema = _parquet_schema(pa)
    table = pa.Table.from_pylist(rows, schema=schema)
    if table.num_rows != len(rows) or table.to_pylist() != rows:
        raise ResearchContractError("Arrow conversion changed source precision/rows")
    artifact_root.mkdir(parents=True, exist_ok=True)
    final = artifact_root / provenance["run_id"] / digest
    # No network, no remote publication, no DB writes; local temp files only.
    if final.exists():
        old = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
        if (old.get("logical_sha256") != digest
                or old.get("version") != VERSION
                or old.get("run_id") != provenance["run_id"]
                or old.get("database") != provenance["database"]
                or old.get("warehouse_schema") != provenance["schema"]
                or old.get("source_total_reported") != provenance["source_total_reported"]
                or old.get("exported_observations") != len(rows)
                or old.get("arrow_schema") != str(schema)):
            raise ResearchContractError("Existing content-addressed dataset is incompatible")
        _verify_existing(final, old, rows)
        if json.loads((final / "audit.json").read_text(encoding="utf-8")) != audit:
            raise ResearchContractError("Existing audit differs from current research profile")
        return {"status": "PASS_EXISTING_IMMUTABLE_PARQUET", "path": str(final),
                "logical_sha256": digest, "parquet_sha256": old["files"]["credit_period.parquet"]["sha256"],
                "row_count": len(rows), "reused": True}
    staging = Path(tempfile.mkdtemp(prefix=".flowwatch-day1-", dir=artifact_root))
    try:
        pq.write_table(
            table, staging / "credit_period.parquet", compression="zstd",
            version="2.6", use_dictionary=False,
        )
        if pq.read_table(staging / "credit_period.parquet").to_pylist() != rows:
            raise ResearchContractError("Parquet round-trip does not equal exact source rows")
        (staging / "audit.json").write_bytes(_json_bytes(audit))
        manifest = {
            "version": VERSION,
            "logical_sha256": digest,
            "run_id": provenance["run_id"],
            "database": provenance["database"],
            "warehouse_schema": provenance["schema"],
            "source_total_reported": provenance["source_total_reported"],
            "exported_observations": len(rows),
            "arrow_schema": str(schema),
            "pyarrow_version": pa.__version__,
            "financial_precision": "Decimal128(24,2); service rate Decimal128(12,6)",
            "forecasting_readiness": "NOT_ESTABLISHED",
            "upstream_point_in_time_consistency": "NOT_GUARANTEED",
            "files": {
                filename: {"sha256": sha256_file(staging / filename),
                           "size_bytes": (staging / filename).stat().st_size}
                for filename in ("credit_period.parquet", "audit.json")
            },
        }
        (staging / "manifest.json").write_bytes(_json_bytes(manifest))
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists():
            raise ResearchContractError("Concurrent publication conflict; rerun to verify")
        staging.rename(final)
        return {"status": "PASS_NEW_IMMUTABLE_PARQUET", "path": str(final),
                "logical_sha256": digest,
                "parquet_sha256": manifest["files"]["credit_period.parquet"]["sha256"],
                "row_count": len(rows), "reused": False}
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def run_gate(run_id: UUID, *, export: bool = False, report: Path = DEFAULT_REPORT) -> dict[str, Any]:
    host, port, password = _connection_settings()
    engine = connect_isolated(host, port, password)
    try:
        with engine.connect() as connection:
            rows, provenance = _read_snapshot(connection, run_id)
        audit = coverage_audit(rows)
        digest = canonical_digest(rows)
        output: dict[str, Any] = {
            "status": "PASS_RESEARCH_AUDIT_PREFLIGHT",
            "exported": False, "version": VERSION,
            "provenance": provenance,
            "logical_sha256": digest,
            "research_audit": audit,
            "limitations": [
                "Only this 3,000-record bounded capture, not the full upstream dataset.",
                "No point-in-time snapshot guarantee across independently fetched API pages.",
                "Per-credit observations are temporally dependent, not independent samples.",
                "No causal, cash-flow, forecasting-label, or model-performance claims.",
            ],
        }
        if export:
            publication = publish_parquet(rows, audit, provenance, digest)
            output["status"] = "PASS_DAY1_BOUNDED_RESEARCH_EXPORT"
            output["exported"] = True
            output["artifact"] = publication
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_bytes(_json_bytes(output))
        return output
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, type=UUID)
    parser.add_argument("--export", action="store_true", help="Publish immutable local Parquet dataset")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    result = run_gate(args.run_id, export=args.export, report=args.report)
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"GATE REPORT: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
