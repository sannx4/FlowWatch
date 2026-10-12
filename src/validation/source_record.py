from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

WORLD_BANK_DATE_FORMAT = "%d-%b-%Y"


NonEmptyString = Annotated[
    str,
    Field(min_length=1),
]


DATE_FIELDS = frozenset(
    {
        "agreement_signing_date",
        "board_approval_date",
        "closed_date_most_recent",
        "effective_date_most_recent",
        "end_of_period",
        "first_repayment_date",
        "last_disbursement_date",
        "last_repayment_date",
    }
)


NULLABLE_DATE_FIELDS = tuple(
    sorted(
        DATE_FIELDS
        - {
            "end_of_period",
        }
    )
)


DECIMAL_FIELDS = frozenset(
    {
        "borrowers_obligation_us_",
        "cancelled_amount_us_",
        "credits_held_us_",
        "disbursed_amount_us_",
        "due_3rd_party_us_",
        "due_to_ida_us_",
        "exchange_adjustment_us_",
        "original_principal_amount_us_",
        "repaid_3rd_party_us_",
        "repaid_to_ida_us_",
        "service_charge_rate",
        "sold_3rd_party_us_",
        "undisbursed_amount_us_",
    }
)


INTEGER_FIELDS = frozenset(
    {
        "board_approval___calendar_year",
        "board_approval___fiscal_year",
    }
)


IDENTIFIER_FIELDS = frozenset(
    {
        "country",
        "country_code",
        "credit_number",
        "project_id",
        "region",
    }
)


_INTEGER_PATTERN = re.compile(
    r"^[+-]?\d+$"
)


def _parse_world_bank_date(
    value: Any,
    *,
    nullable: bool,
) -> date | None:
    """
    Parse the World Bank source date representation.

    ValueError is intentionally used for invalid source input so
    Pydantic converts the failure into a ValidationError that the
    quarantine service can handle.
    """

    if value is None:
        if nullable:
            return None

        raise ValueError(
            "date is required"
        )

    if isinstance(
        value,
        datetime,
    ):
        raise ValueError(  # noqa: TRY004
            "datetime values are not valid source dates"
        )

    if isinstance(
        value,
        date,
    ):
        return value

    if not isinstance(
        value,
        str,
    ):
        raise ValueError(  # noqa: TRY004
            "date must be a DD-Mon-YYYY string"
        )

    text = value.strip()

    if not text:
        raise ValueError(
            "date cannot be blank"
        )

    try:
        return datetime.strptime(
            text,
            WORLD_BANK_DATE_FORMAT,
        ).date()

    except ValueError as exc:
        raise ValueError(
            "invalid World Bank date; "
            "expected DD-Mon-YYYY"
        ) from exc


def _parse_decimal(
    value: Any,
) -> Decimal | None:
    """
    Parse an observed World Bank numeric representation.

    Native integers, floats, Decimal values, numeric strings, and
    nulls are supported explicitly.
    """

    if value is None:
        return None

    if isinstance(
        value,
        bool,
    ):
        raise ValueError(  # noqa: TRY004
            "boolean is not a valid numeric value"
        )

    result: Decimal

    if isinstance(
        value,
        Decimal,
    ):
        result = value

    elif isinstance(
        value,
        int,
    ):
        result = Decimal(
            value
        )

    elif isinstance(
        value,
        float,
    ):
        result = Decimal(
            str(
                value
            )
        )

    elif isinstance(
        value,
        str,
    ):
        text = value.strip()

        if not text:
            raise ValueError(
                "numeric value cannot be blank"
            )

        try:
            result = Decimal(
                text
            )

        except InvalidOperation as exc:
            raise ValueError(
                "invalid numeric value"
            ) from exc

    else:
        raise ValueError(  # noqa: TRY004
            "numeric value must be an "
            "integer, float, Decimal, "
            "numeric string, or null"
        )

    if not result.is_finite():
        raise ValueError(
            "numeric value must be finite"
        )

    return result


def _parse_integer(
    value: Any,
) -> int | None:
    """
    Parse an integer-valued source field.

    Integer strings are accepted explicitly, but fractional values,
    booleans, and arbitrary objects are rejected.
    """

    if value is None:
        return None

    if isinstance(
        value,
        bool,
    ):
        raise ValueError(  # noqa: TRY004
            "boolean is not a valid integer"
        )

    if isinstance(
        value,
        int,
    ):
        return value

    if isinstance(
        value,
        str,
    ):
        text = value.strip()

        if (
            not text
            or not _INTEGER_PATTERN.fullmatch(
                text
            )
        ):
            raise ValueError(
                "invalid integer value"
            )

        return int(
            text
        )

    raise ValueError(
        "integer value must be an integer, "
        "integer string, or null"
    )


class WorldBankSourceRecord(
    BaseModel
):
    """
    Typed representation of one World Bank source record.

    This model performs source parsing only.

    It deliberately does not create canonical Country, Project,
    Credit, or CreditSnapshot business objects.
    """

    model_config = ConfigDict(
        extra="allow",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )

    agreement_signing_date: date | None
    board_approval_date: date | None

    borrower: str | None

    borrowers_obligation_us_: Decimal | None

    board_approval___fiscal_year: int | None
    board_approval___calendar_year: int | None

    cancelled_amount_us_: Decimal | None

    closed_date_most_recent: date | None

    country: NonEmptyString
    country_code: NonEmptyString

    credit_number: NonEmptyString

    credit_status: str | None

    credits_held_us_: Decimal | None

    currency_of_commitment: str | None

    disbursed_amount_us_: Decimal | None
    due_3rd_party_us_: Decimal | None
    due_to_ida_us_: Decimal | None

    effective_date_most_recent: date | None

    end_of_period: date

    exchange_adjustment_us_: Decimal | None

    first_repayment_date: date | None
    last_disbursement_date: date | None
    last_repayment_date: date | None

    original_principal_amount_us_: Decimal | None

    project_id: NonEmptyString
    project_name: str | None

    region: NonEmptyString

    repaid_3rd_party_us_: Decimal | None
    repaid_to_ida_us_: Decimal | None

    service_charge_rate: Decimal | None

    sold_3rd_party_us_: Decimal | None

    undisbursed_amount_us_: Decimal | None

    @field_validator(
        "end_of_period",
        mode="before",
    )
    @classmethod
    def parse_required_end_of_period(
        cls,
        value: Any,
    ) -> date:
        parsed = _parse_world_bank_date(
            value,
            nullable=False,
        )

        assert parsed is not None

        return parsed

    @field_validator(
        *NULLABLE_DATE_FIELDS,
        mode="before",
    )
    @classmethod
    def parse_nullable_date_fields(
        cls,
        value: Any,
    ) -> date | None:
        return _parse_world_bank_date(
            value,
            nullable=True,
        )

    @field_validator(
        *sorted(
            DECIMAL_FIELDS
        ),
        mode="before",
    )
    @classmethod
    def parse_decimal_fields(
        cls,
        value: Any,
    ) -> Decimal | None:
        return _parse_decimal(
            value
        )

    @field_validator(
        *sorted(
            INTEGER_FIELDS
        ),
        mode="before",
    )
    @classmethod
    def parse_integer_fields(
        cls,
        value: Any,
    ) -> int | None:
        return _parse_integer(
            value
        )