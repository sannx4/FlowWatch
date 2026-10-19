# FlowWatch — Day 22 Research-Integrity Evidence

**Status:** Implementation prepared; repository-local tests and real-fixture parity must pass before approval.

## Primary threat: decimal distortion

The point-forecast target is based on financial disbursement ratios. Rounding binary floating-point inputs, coercing invalid financial fields to zero, or quantizing prematurely may alter the ratio used to compute 3/6/12-month forecast errors. Residual magnitude is the **central empirical quantity** in the planned cross-horizon conformal study. A tiny systematic perturbation could change tail nonconformity scores, coverage decisions and ranking between baseline and proposed methods.

**Control:** `optional_decimal()` returns finite `Decimal` from exact text, integer or existing `Decimal`, refuses `float`, and does not quantize. Reproducible test: `test_exact_decimal_precision_and_scale` and `test_lossy_or_invalid_numeric_values_fail` in `tests/unit/test_day22_pure_transformation.py`.

**Caveat:** Raw JSON decoding must use `parse_float=Decimal` where native numeric literals appear. The SQL target NUMERIC precision and scale require separate round-trip verification.

## Reporting-date distortion and label maturity

Converting an invalid, missing or offset timestamp to an arbitrary period could shift a historical observation across forecast-origin or label-maturity boundaries. In later cross-horizon experiments this could produce forward-information leakage, contaminate training/validation splits, or make a 12-month outcome seem available too early.

**Control:** required `end_of_period`; World Bank `DD-Mon-YYYY`, ISO calendar dates or UTC-midnight timestamps; malformed and non-midnight values fail closed. Reproducible tests: `test_supported_calendar_dates`, `test_malformed_or_ambiguous_dates_fail`, `test_required_fields_reject_empty`.

## Source-field / category distortion

Mistaken mappings from source amounts to canonical money columns or confusing `credit_status` (historically variable) with a stable credit field would change empirical groupings and longitudinal trajectories. Null-to-zero coercion could fabricate cash flows and lead to biased project-level growth or portfolio risk estimates.

**Control:** versioned mapping table, separate snapshot/credit dictionaries and explicit null semantics. Reproducible tests: `test_entities_and_snapshot_are_separate_pure_mappings`, `test_missing_optional_money_fields_are_null`, and the 100-row `scripts/day22_parity_audit.py`.

## Nondeterministic feature substrate

If the same raw source bytes yielded different canonical values across executions, later forecast/interval metrics could not be tied to a stable dataset version or code version.

**Control:** pure functions with no I/O and no mutation, repeatable canonical SHA-256 fingerprints, positive Day-7 fixture parity. Reproducible tests: `test_canonical_repeatedly_equal_without_source_mutation`, `test_fingerprint_unaffected_by_input_order`, `test_parity_with_day07_on_valid_reference_fixture`.

## Evidence gate

Before claiming Day 22 complete in the local repository:

1. Run Ruff + mypy + entire pytest suite.
2. Run real-source parity audit; retain **both successful and mismatched** field evidence.
3. Do not activate new mapper in loader while the audit fails.
4. Record any intentionally changed parsing contract as a versioned transformation change, not as a silent fix.
5. Preserve Day-21 Mongo envelope lineage and restricted-role loading contracts unchanged.

**Research claim:** reliability and test coverage of input conversions only, NOT evidence that forecasting or MACH-CP improves uncertainty calibration.
