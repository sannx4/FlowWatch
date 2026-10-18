"""Day 18: pure analysis of retained raw documents, without source IO."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


def _payload_of(
    document: Mapping[str, Any],
) -> Mapping[str, Any]:
    payload = document.get("payload")

    if not isinstance(payload, dict):
       raise TypeError(
        "Raw record must have a mapping payload"
    )

    return payload


def _type_label(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"

    return type(value).__name__


def _run_metadata(
    documents: Sequence[Mapping[str, Any]],
) -> dict[str, str]:
    if not documents:
        raise ValueError(
            "Cannot inspect an empty raw run"
        )

    result: dict[str, str] = {}

    for name in (
        "run_id",
        "dataset_id",
        "resource_id",
    ):
        values = {
            str(document.get(name, ""))
            for document in documents
        }

        if len(values) != 1 or not next(iter(values)):
            raise ValueError(
                f"Inconsistent or missing {name} in raw run"
            )

        result[name] = next(iter(values))

    return result


def profile_raw_run(
    documents: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return schema, missingness and identifier statistics."""
    metadata = _run_metadata(documents)

    appearances: Counter[str] = Counter()

    observed_types: dict[
        str, Counter[str]
    ] = {}

    identities: Counter[
        tuple[str, str]
    ] = Counter()

    incomplete_identities = 0

    raw_record_keys: Counter[str] = Counter()

    for document in documents:
        payload = _payload_of(document)

        for field, value in payload.items():
            appearances[field] += 1

            observed_types.setdefault(
                field,
                Counter(),
            )[_type_label(value)] += 1

        credit = payload.get("credit_number")
        period = payload.get("end_of_period")

        if credit is None or period is None:
            incomplete_identities += 1
        else:
            identities[
                (str(credit), str(period))
            ] += 1

        key = document.get("source_record_key")

        if key:
            raw_record_keys[str(key)] += 1

    row_count = len(documents)

    return {
        **metadata,
        "record_count_examined": row_count,
        "distinct_business_identities": len(identities),
        "duplicate_business_identity_count": sum(
            count - 1
            for count in identities.values()
            if count > 1
        ),
        "missing_business_identity_count": incomplete_identities,
        "duplicate_source_record_keys": sum(
            count - 1
            for count in raw_record_keys.values()
            if count > 1
        ),
        "field_profile": {
            field: {
                "present": appearances[field],
                "missing": row_count - appearances[field],
                "types": dict(
                    sorted(observed_types[field].items())
                ),
            }
            for field in sorted(appearances)
        },
    }


def _business_map(
    documents: Sequence[Mapping[str, Any]],
) -> dict[tuple[str, str], str]:
    result: dict[tuple[str, str], str] = {}

    for document in documents:
        payload = _payload_of(document)

        credit = payload.get("credit_number")
        period = payload.get("end_of_period")

        if credit is None or period is None:
            continue

        identity = (
            str(credit),
            str(period),
        )

        raw_json = json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )

        digest = hashlib.sha256(
            raw_json.encode("utf-8")
        ).hexdigest()

        if identity in result and result[identity] != digest:
            raise ValueError(
                "Conflicting payloads for the same business identity "
                "within one source run; drift comparison is ambiguous"
            )

        result[identity] = digest

    return result


def compare_raw_runs(
    baseline_documents: Sequence[Mapping[str, Any]],
    comparison_documents: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare comparable stored runs using business identities."""
    before = profile_raw_run(baseline_documents)
    after = profile_raw_run(comparison_documents)

    if before["run_id"] == after["run_id"]:
        raise ValueError(
            "Comparison requires two different ingestion runs"
        )

    for field in (
        "dataset_id",
        "resource_id",
    ):
        if before[field] != after[field]:
            raise ValueError(
                f"Incomparable source runs: different {field}"
            )

    older = _business_map(baseline_documents)
    newer = _business_map(comparison_documents)

    shared = older.keys() & newer.keys()

    fields_before = set(before["field_profile"])
    fields_after = set(after["field_profile"])

    return {
        "status": "COMPARED_STORED_RUNS",
        "dataset_id": before["dataset_id"],
        "resource_id": before["resource_id"],
        "baseline_run_id": before["run_id"],
        "comparison_run_id": after["run_id"],
        "baseline_records_examined": before[
            "record_count_examined"
        ],
        "comparison_records_examined": after[
            "record_count_examined"
        ],
        "matched_business_identities": len(shared),
        "changed_payloads_among_matched": sum(
            older[identity] != newer[identity]
            for identity in shared
        ),
        "new_business_identities": len(
            newer.keys() - older.keys()
        ),
        "missing_business_identities": len(
            older.keys() - newer.keys()
        ),
        "fields_added": sorted(
            fields_after - fields_before
        ),
        "fields_removed": sorted(
            fields_before - fields_after
        ),
        "types_changed_for_common_fields": sorted(
            field
            for field in fields_before & fields_after
            if before["field_profile"][field]["types"].keys()
            != after["field_profile"][field]["types"].keys()
        ),
        "interpretation": (
            "This is observed source-data/schema variation, not a "
            "forecast-error or model-drift conclusion. Counts refer "
            "only to the selected stored records."
        ),
    }