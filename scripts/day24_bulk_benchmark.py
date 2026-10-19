"""Controlled Day-24 row-UPSERT vs COPY/staging benchmark on real source records.

Neither benchmark path commits: a rollback resets the identical starting state.
The target is *only* flowwatch_day24_gate, accessed as flowwatch_ingestor.

Run: python -m scripts.day24_bulk_benchmark --sizes 5 25 50 100 --repeats 3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
from datetime import UTC, datetime
from decimal import Decimal
from getpass import getpass
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from dotenv import load_dotenv
from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Connection

from src.loaders.day23_upsert import (
    CanonicalInput,
    SnapshotCorrectionRequired,
    SourceIdentity,
    load_exact_batch,
    load_exact_record,
)
from src.loaders.day24_bulk import load_bulk_batch
from src.transformation.pure import transform_canonical_record

TARGET_DATABASE = "flowwatch_day24_gate"
DEFAULT_SOURCE = Path("data/raw/world_bank_sample.json")
REPORT_PATH = Path("benchmarks/day24/initial-ingestion-benchmark.json")
ENTITIES = ("regions", "countries", "projects", "credits", "credit_snapshots")


def _load_source(source: Path, n: int) -> tuple[list[CanonicalInput], str, int]:
    original = source.read_bytes()
    checksum = hashlib.sha256(original).hexdigest()
    payload = json.loads(original, parse_float=Decimal)
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise TypeError("World Bank source file must contain a data list")
    items = payload["data"]
    if len(items) < n:
        raise ValueError(f"Source contains {len(items)} records, need {n}")
    records = []
    run_id = uuid5(NAMESPACE_URL, f"flowwatch:day24:offline-file:{checksum}")
    for index, raw in enumerate(items[:n]):
        if not isinstance(raw, dict):
            raise TypeError("Expected World Bank record object")
        records.append(CanonicalInput(
            payload=raw,
            lineage=SourceIdentity(
                run_id=run_id,
                source_checksum=checksum,
                source_record_key=f"day24:offline-fixture:{checksum}:{index}",
            ),
        ))
    # These represent *source-file* identities for a rolled-back benchmark,
    # not MongoDB run IDs or persisted ingestion evidence.
    return records, checksum, len(items)


def _verify_target(connection: Connection) -> None:
    name, session, current = connection.execute(
        text("SELECT current_database(), session_user, current_user")
    ).one()
    if (name, session, current) != (
        TARGET_DATABASE, "flowwatch_ingestor", "flowwatch_ingestor"
    ):
        raise RuntimeError("REFUSING: benchmark requires isolated DB and ingestor role")


def _counts(connection: Connection) -> dict[str, int]:
    return {name: int(connection.execute(
        text(f"SELECT COUNT(*) FROM public.{name}")
    ).scalar_one()) for name in ENTITIES}


def _normalized_result(
    connection: Connection, records: list[CanonicalInput],
) -> list[tuple[str, ...]]:
    # Fetch precisely the tested snapshot identities; exclude generated IDs,
    # created_at, and DB sequences (they intentionally differ after rollback).
    credit_numbers = {str(r.payload["credit_number"]) for r in records}
    stmt = text("""
        SELECT c.credit_number, s.end_of_period, s.credit_status,
               s.service_charge_rate, s.original_principal_amount_usd,
               s.cancelled_amount_usd, s.undisbursed_amount_usd,
               s.disbursed_amount_usd, s.repaid_to_ida_usd, s.due_to_ida_usd,
               s.exchange_adjustment_usd, s.borrowers_obligation_usd,
               s.sold_third_party_usd, s.repaid_third_party_usd,
               s.due_third_party_usd, s.credits_held_usd,
               s.last_disbursement_date,
               s.ingestion_run_id, s.source_checksum, s.source_record_key,
               c.borrower, c.currency_of_commitment, c.board_approval_date,
               c.agreement_signing_date, c.effective_date, c.first_repayment_date,
               c.last_repayment_date, c.closed_date,
               p.project_id, p.project_name,
               co.country_code, co.country_name, re.region_name
        FROM public.credit_snapshots s
        JOIN public.credits c ON c.credit_id = s.credit_id
        JOIN public.projects p ON p.project_pk = c.project_pk
        JOIN public.countries co ON co.country_id = p.country_id
        JOIN public.regions re ON re.region_id = co.region_id
        WHERE c.credit_number = ANY(:credit_numbers)
    """)
    rows = connection.execute(stmt, {"credit_numbers": list(credit_numbers)}).all()
    identity_set = {
        (str(r.payload["credit_number"]),
         str(transform_canonical_record(r.payload)["snapshot"]["end_of_period"]))
        for r in records
    }
    filtered = [tuple(str(value) if value is not None else "<NULL>" for value in row)
                for row in rows if (str(row[0]), str(row[1])) in identity_set]
    if len(filtered) != len(records):
        raise AssertionError(
            f"Expected {len(records)} distinct tested snapshots, got {len(filtered)}"
        )
    if len({(row[0], row[1]) for row in filtered}) != len(filtered):
        raise AssertionError("Duplicate (credit_number, end_of_period) identity")
    return sorted(filtered)


def _one_trial(
    engine: Any,
    records: list[CanonicalInput],
    method: str,
) -> dict[str, Any]:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            _verify_target(connection)
            t0 = perf_counter()
            if method == "reference_row":
                loaded, actions = load_exact_batch(connection, records)
                extras: dict[str, Any] = {
                    "loaded_records": len(loaded), "operations": actions
                }
            else:
                result = load_bulk_batch(connection, records)
                extras = {
                    "loaded_records": result.input_records,
                    "inserted": result.inserted,
                    "updated": result.updated,
                    "unchanged": result.unchanged,
                    "ignored": result.ignored,
                    "copy_seconds": result.copy_seconds,
                    "merge_seconds": result.merge_seconds,
                    "entity_seconds": result.entity_seconds,
                }
            elapsed = perf_counter() - t0
            values = _normalized_result(connection, records)
            counts = _counts(connection)
            return {
                "method": method,
                "elapsed_seconds": elapsed,
                "records_per_second": len(records) / elapsed,
                "snapshot_values": values,
                "counts": counts,
                **extras,
            }
        finally:
            transaction.rollback()


def _run_trials(
    engine: Any, records: list[CanonicalInput], sizes: list[int], repeats: int,
) -> list[dict[str, Any]]:
    results = []
    for n in sizes:
        sample = records[:n]
        trials: dict[str, list[dict[str, Any]]] = {"reference_row": [], "bulk_copy": []}
        # Alternating methods reduces—but does not eliminate—order effects.
        for repeat in range(repeats):
            order = ("reference_row", "bulk_copy") if repeat % 2 == 0 else (
                "bulk_copy", "reference_row"
            )
            observed: dict[str, dict[str, Any]] = {}
            for method in order:
                result = _one_trial(engine, sample, method)
                trials[method].append({k: v for k, v in result.items()
                                       if k != "snapshot_values"})
                observed[method] = result
            if observed["reference_row"]["snapshot_values"] != observed["bulk_copy"]["snapshot_values"]:
                raise AssertionError(f"Snapshot business values/lineage differ at size {n}")
            if observed["reference_row"]["counts"] != observed["bulk_copy"]["counts"]:
                raise AssertionError(f"Canonical entity/snapshot counts differ at size {n}")
        ref = [x["elapsed_seconds"] for x in trials["reference_row"]]
        bulk = [x["elapsed_seconds"] for x in trials["bulk_copy"]]
        ref_median = statistics.median(ref)
        bulk_median = statistics.median(bulk)
        group = {
            "n": n,
            "repeats": repeats,
            "reference_row": trials["reference_row"],
            "bulk_copy": trials["bulk_copy"],
            "median_reference_seconds": ref_median,
            "median_bulk_seconds": bulk_median,
            "median_speedup_reference_div_bulk": ref_median / bulk_median,
            "canonical_values_identical": True,
            "canonical_table_counts_identical": True,
        }
        results.append(group)
        print(
            f"n={n:>4} row median={ref_median:.4f}s "
            f"bulk median={bulk_median:.4f}s "
            f"speedup={ref_median / bulk_median:.2f}x; parity PASS"
        )
    return results



def _controlled_correction_probe(engine: Any, original: CanonicalInput) -> dict[str, bool]:
    """Compare Day-23/Day-24 correction behavior in rolled-back transactions.

    The correction is deliberately synthetic; it is NEVER written persistently
    and is not presented as evidence of an actual upstream source correction.
    """
    corrected = dict(original.payload)
    corrected["credit_status"] = (
        f"{corrected.get('credit_status') or 'UNKNOWN'} [DAY24 CONTROLLED TEST]"
    )
    simulated = CanonicalInput(
        payload=corrected,
        lineage=SourceIdentity(
            run_id=original.lineage.run_id,
            source_checksum=hashlib.sha256(
                json.dumps(corrected, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest(),
            source_record_key=original.lineage.source_record_key + ":day24-correction",
        ),
    )
    captured: dict[str, list[tuple[str, ...]]] = {}
    for method in ("reference_row", "bulk_copy"):
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                _verify_target(connection)

                def load(item: CanonicalInput, policy: str, selected_method: str = method) -> Any:
                    if selected_method == "reference_row":
                        return load_exact_record(
                            connection, item, snapshot_policy=policy  # type: ignore[arg-type]
                        )
                    return load_bulk_batch(
                        connection, [item], snapshot_policy=policy  # type: ignore[arg-type]
                    )

                load(original, "reject")
                baseline = _normalized_result(connection, [original])
                try:
                    load(simulated, "reject")
                except SnapshotCorrectionRequired:
                    pass
                else:
                    raise AssertionError(f"{method}: default reject failed")

                load(simulated, "ignore")
                if _normalized_result(connection, [original]) != baseline:
                    raise AssertionError(f"{method}: ignore changed persisted values")

                load(simulated, "update")
                revised = _normalized_result(connection, [simulated])
                if revised == baseline:
                    raise AssertionError(f"{method}: explicit update was not applied")
                captured[method] = revised

                # The same source key must never produce different canonical values.
                stale_key = CanonicalInput(
                    payload=original.payload,
                    lineage=simulated.lineage,
                )
                try:
                    load(stale_key, "update")
                except SnapshotCorrectionRequired:
                    pass
                else:
                    raise AssertionError(f"{method}: same-key value drift not rejected")
            finally:
                transaction.rollback()
    if captured["reference_row"] != captured["bulk_copy"]:
        raise AssertionError("Correction policy results differ between loaders")
    return {
        "reject": True, "ignore": True, "explicit_update": True,
        "same_key_divergence_rejected": True, "rollback_only": True,
        "reference_bulk_same_result": True,
    }


def _three_pass_replay_probe(engine: Any, records: list[CanonicalInput]) -> dict[str, Any]:
    """Three bulk loads in one rolled-back transaction; checks no-op semantics."""
    batch = records[:5]
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            _verify_target(connection)
            counts = []
            inserted = []
            ids = []
            for _ in range(3):
                result = load_bulk_batch(connection, batch)
                counts.append(_counts(connection))
                inserted.append(result.inserted)
                ids.append(result.snapshot_ids)
            if not (counts[0] == counts[1] == counts[2]):
                raise AssertionError("Bulk replay changed canonical counts")
            if not (ids[0] == ids[1] == ids[2]):
                raise AssertionError("Bulk replay changed snapshot IDs")
            if inserted != [len(batch), 0, 0]:
                raise AssertionError(f"Unexpected bulk inserted rows per replay: {inserted}")
            return {
                "passes": 3, "batch_size": len(batch),
                "inserted_per_pass": inserted,
                "stable_ids": True, "stable_counts": True,
                "probe_rolled_back": True,
            }
        finally:
            transaction.rollback()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--sizes", nargs="+", type=int, default=[5, 25, 50, 100])
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if not args.sizes or any(n <= 0 for n in args.sizes) or args.repeats < 2:
        parser.error("Sizes must be positive and repeats must be >= 2")
    source_path: Path = args.source
    if not source_path.is_file():
        parser.error(f"Source fixture missing: {source_path}")

    load_dotenv()
    host = os.getenv("POSTGRES_HOST", "127.0.0.1")
    if host not in ("localhost", "127.0.0.1"):
        raise RuntimeError("REFUSING: local PostgreSQL only")
    items, sha, available = _load_source(source_path, max(args.sizes))
    print(f"Real World Bank fixture: {available} records, SHA-256 {sha}")
    password = getpass("Password for PostgreSQL flowwatch_ingestor: ")
    engine = create_engine(
        URL.create(
            "postgresql+psycopg",
            username="flowwatch_ingestor", password=password,
            host=host, port=int(os.getenv("POSTGRES_PORT", "5434")),
            database=TARGET_DATABASE,
        ),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )
    del password
    try:
        with engine.connect() as connection:
            _verify_target(connection)
            counts_before = _counts(connection)
            if counts_before["credit_snapshots"] != 0:
                raise RuntimeError(
                    "REFUSING: isolated Day-24 DB must have zero snapshots. "
                    "Inspect it and TRUNCATE only that isolated database."
                )
            pg_version = str(connection.execute(text("SHOW server_version")).scalar_one())
        benchmark = _run_trials(engine, items, sorted(set(args.sizes)), args.repeats)
        corrections = _controlled_correction_probe(engine, items[0])
        replays = _three_pass_replay_probe(engine, items)
        with engine.connect() as connection:
            _verify_target(connection)
            counts_after = _counts(connection)
        if counts_after != counts_before:
            raise AssertionError("Rollback benchmark modified persisted canonical rows")
    finally:
        engine.dispose()

    report = {
        "status": "PASS_DAY24_ROLLBACK_BENCHMARK",
        "tested_at_utc": datetime.now(UTC).isoformat(),
        "db": TARGET_DATABASE,
        "role": "flowwatch_ingestor",
        "source_kind": "real_world_bank_offline_json_fixture",
        "source_path": str(source_path),
        "source_sha256": sha,
        "source_file_records_available": available,
        "source_api_contacted": False,
        "source_mongodb_mutated": False,
        "committed_database_changes": False,
        "postgres_version": pg_version,
        "python_version": platform.python_version(),
        "counts_before": counts_before,
        "counts_after": counts_after,
        "results": benchmark,
        "controlled_correction_probe": corrections,
        "bulk_three_pass_replay": replays,
        "limitations": [
            "Initial laptop benchmark: no concurrent writers and no throughput SLA claim.",
            "Whole-path timing includes entity upserts; COPY is only the snapshot phase.",
            "Benchmark source is a real offline sample, not a new MongoDB ingestion run.",
            "Only original source observations are used; no generated samples.",
            "Temporary staging and canonical writes are unconditionally rolled back.",
            "Source correction ordering still needs a production precedence rule.",
        ],
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Day 24: PASS, reference/bulk parity across sizes, report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
