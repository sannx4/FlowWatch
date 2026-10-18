
"""Machine-readable quality rules for World Bank source records."""

from __future__ import annotations

from enum import StrEnum

from src.validation.models import RejectionIssue, RejectionReasonCode
from src.validation.source_record import (
    DATE_FIELDS,
    DECIMAL_FIELDS,
    IDENTIFIER_FIELDS,
    INTEGER_FIELDS,
)


class QualityRuleId(StrEnum):
    INVALID_RECORD_TYPE = "DQ-SRC-001"
    INVALID_SOURCE_VALUE = "DQ-SRC-002"

    INVALID_CREDIT_NUMBER = "DQ-ID-001"
    INVALID_PROJECT_ID = "DQ-ID-002"
    INVALID_ENTITY_IDENTIFIER = "DQ-ID-003"

    INVALID_REPORTING_DATE = "DQ-TEMP-001"
    DUPLICATE_CREDIT_PERIOD = "DQ-TEMP-002"
    CONFLICTING_CREDIT_PERIOD = "DQ-TEMP-003"

    INVALID_OPTIONAL_DATE = "DQ-DATE-001"
    UNEXPECTED_DATE_ORDER = "DQ-DATE-002"

    INVALID_DECIMAL = "DQ-AMOUNT-001"
    DISBURSEMENT_EXCEEDS_PRINCIPAL = "DQ-AMOUNT-002"

    FINANCIAL_COMPONENT_MISMATCH = "DQ-CROSS-001"

    INVALID_INTEGER = "DQ-SCHEMA-001"


RULE_CATALOG: dict[QualityRuleId, str] = {
    QualityRuleId.INVALID_RECORD_TYPE:
        "Source record must be a JSON object.",
    QualityRuleId.INVALID_SOURCE_VALUE:
        "Source field failed schema validation.",
    QualityRuleId.INVALID_CREDIT_NUMBER:
        "Credit number must be present and non-empty.",
    QualityRuleId.INVALID_PROJECT_ID:
        "Project ID must be present and non-empty.",
    QualityRuleId.INVALID_ENTITY_IDENTIFIER:
        "Required country or region identifier is invalid.",
    QualityRuleId.INVALID_REPORTING_DATE:
        "Reporting period must be a valid required date.",
    QualityRuleId.DUPLICATE_CREDIT_PERIOD:
        "Credit and reporting period repeat with identical source content.",
    QualityRuleId.CONFLICTING_CREDIT_PERIOD:
        "Credit and reporting period repeat with different source content.",
    QualityRuleId.INVALID_OPTIONAL_DATE:
        "An optional source date has an invalid representation.",
    QualityRuleId.UNEXPECTED_DATE_ORDER:
        "Source dates have an unexpected chronological relationship.",
    QualityRuleId.INVALID_DECIMAL:
        "A financial numeric field must contain a finite decimal.",
    QualityRuleId.DISBURSEMENT_EXCEEDS_PRINCIPAL:
        "Disbursed amount exceeds original principal; investigate.",
    QualityRuleId.FINANCIAL_COMPONENT_MISMATCH:
        "Financial components differ from original principal; investigate.",
    QualityRuleId.INVALID_INTEGER:
        "An integer-valued source field is invalid.",
}


WARNING_RULE_IDS = frozenset(
    {
        QualityRuleId.UNEXPECTED_DATE_ORDER,
        QualityRuleId.DISBURSEMENT_EXCEEDS_PRINCIPAL,
        QualityRuleId.FINANCIAL_COMPONENT_MISMATCH,
    }
)


def rule_id_for_issue(issue: RejectionIssue) -> QualityRuleId:
    """Map an existing source rejection to a stable quality-rule ID."""

    if issue.reason_code == RejectionReasonCode.INVALID_RECORD_TYPE:
        return QualityRuleId.INVALID_RECORD_TYPE

    field = issue.field_path.split(".", maxsplit=1)[0]

    if field == "credit_number":
        return QualityRuleId.INVALID_CREDIT_NUMBER

    if field == "project_id":
        return QualityRuleId.INVALID_PROJECT_ID

    if field == "end_of_period":
        return QualityRuleId.INVALID_REPORTING_DATE

    if field in IDENTIFIER_FIELDS:
        return QualityRuleId.INVALID_ENTITY_IDENTIFIER

    if field in DATE_FIELDS:
        return QualityRuleId.INVALID_OPTIONAL_DATE

    if field in DECIMAL_FIELDS:
        return QualityRuleId.INVALID_DECIMAL

    if field in INTEGER_FIELDS:
        return QualityRuleId.INVALID_INTEGER

    return QualityRuleId.INVALID_SOURCE_VALUE
