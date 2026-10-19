# FlowWatch Day 22 — Source-to-canonical mapping v0.1

## Contract

This mapping is **pure**: `transform_canonical_record(source)` returns newly allocated Python dictionaries and performs no I/O, SQL, logging, timezone conversion, clock access, or mutation. It matches the five dictionary groups already consumed by the PostgreSQL loader: `region`, `country`, `project`, `credit`, `snapshot`.

**Source authority:** World Bank IDA Statement of Credits records retained verbatim in MongoDB. **Lineage authority:** `RawRecordEnvelope` supplies `run_id`, `source_checksum`, `source_record_key`; transformations must NOT derive/replace them. Foreign-key IDs (`region_id`, `country_id`, `project_pk`, `credit_id`) remain database concerns.

| Canonical entity | Target field | Source field | Conversion |
|---|---|---|---|
| region | region_name | region | required text |
| country | country_code | country_code | required text |
| country | country_name | country | required text |
| project | project_id | project_id | required text |
| project | project_name | project_name | nullable text |
| credit | credit_number | credit_number | required text |
| credit | borrower | borrower | nullable text |
| credit | currency_of_commitment | currency_of_commitment | nullable text |
| credit | board_approval_date | board_approval_date | nullable source date |
| credit | agreement_signing_date | agreement_signing_date | nullable source date |
| credit | effective_date | effective_date_most_recent | nullable source date |
| credit | first_repayment_date | first_repayment_date | nullable source date |
| credit | last_repayment_date | last_repayment_date | nullable source date |
| credit | closed_date | closed_date_most_recent | nullable source date |
| snapshot | end_of_period | end_of_period | **required** source date |
| snapshot | credit_status | credit_status | nullable text |
| snapshot | service_charge_rate | service_charge_rate | nullable exact decimal |
| snapshot | original_principal_amount_usd | original_principal_amount_us_ | nullable exact decimal |
| snapshot | cancelled_amount_usd | cancelled_amount_us_ | nullable exact decimal |
| snapshot | undisbursed_amount_usd | undisbursed_amount_us_ | nullable exact decimal |
| snapshot | disbursed_amount_usd | disbursed_amount_us_ | nullable exact decimal |
| snapshot | repaid_to_ida_usd | repaid_to_ida_us_ | nullable exact decimal |
| snapshot | due_to_ida_usd | due_to_ida_us_ | nullable exact decimal |
| snapshot | exchange_adjustment_usd | exchange_adjustment_us_ | nullable exact decimal |
| snapshot | borrowers_obligation_usd | borrowers_obligation_us_ | nullable exact decimal |
| snapshot | sold_third_party_usd | sold_3rd_party_us_ | nullable exact decimal |
| snapshot | repaid_third_party_usd | repaid_3rd_party_us_ | nullable exact decimal |
| snapshot | due_third_party_usd | due_3rd_party_us_ | nullable exact decimal |
| snapshot | credits_held_usd | credits_held_us_ | nullable exact decimal |
| snapshot | last_disbursement_date | last_disbursement_date | nullable source date |

## Type / null / failure policy

- **Identifiers:** required, nonempty strings; surrounding whitespace stripped; never invent IDs from other fields.
- **Optional text:** missing, `None` or blank strings become `None`; preserve ordinary case; trim surrounding whitespace. Non-text input fails closed.
- **Dates:** `date`, the World Bank source format `DD-Mon-YYYY` (e.g., `30-Jun-2022`, interpreted with a fixed English month table rather than locale), `YYYY-MM-DD`, or explicit UTC-midnight ISO timestamps such as `2025-06-30T00:00:00.000Z` become `datetime.date`. Optional missing/blank => `None`. Invalid calendar dates, ambiguous formats, non-midnight timestamps and non-UTC offsets fail; never fabricate an observation period.
- **Money and rates:** `Decimal`, integer or base-10 numeric text, including exponent, to `Decimal` without quantizing. Optional missing/blank => `None`; `NaN`, infinity, booleans, float, commas, units and malformed numbers fail. A source JSON literal with decimals must be decoded with `json.loads(data, parse_float=Decimal)` **before** information is rounded in binary. Existing JSON loaded as `float` needs a documented lossless decoding path from original bytes; never silently assert precision has been recovered.
- **Validation:** the Day-12/20 source-quality layer remains the owner of business constraints (amount ranges, cross-field consistency and duplicate credit-period keys). Day 22 focuses on safe representational conversions, not silently correcting business-rule failures.
- **Database decimal scale:** Python `Decimal` preserves base-10 input precision. PostgreSQL NUMERIC column scale may round on insertion; verify database schema and round-trip separately before claiming end-to-end exactness.
- **Source dates are not ISO-only:** the real World Bank sample uses `DD-Mon-YYYY` for reporting periods. This conversion is mandatory for data correctness.
- **No date inference:** a missing optional date stays null; a missing `end_of_period` is invalid.
- **Deterministic fingerprint:** SHA-256 over key-sorted canonical JSON with `Decimal` encoded as string and dates as ISO. This is a transformation-version identity helper, **not** a source checksum or substitute for envelope lineage.

## Migration policy and parity gate

Day 22 initially adds `src/transformation/types.py` and `pure.py` without replacing `day07.py` (the current production loader). Run `python -m scripts.day22_parity_audit` on the real 100-record fixture. A **PASS** plus all regression tests permits a separate, reviewed switch of the loader import to `from src.transformation.pure import transform_canonical_record as transform_record`. A **FAIL** means stop, inspect differences and either fix strict conversion or document an intentional versioned mapping change before changing the loader. The audit intentionally performs no database mutations.

## Evidence

- `tests/unit/test_day22_pure_transformation.py` — pure mapping, deterministic fingerprints, nulls, malformed types, high-precision decimal and Day-7 compatibility fixture.
- `scripts/day22_parity_audit.py` — local 100-row baseline comparison, machine-readable evidence in `reports/day22-transformation-parity.json`.
- `reports/day22-research-integrity.md` — bias risks and causal implications.
