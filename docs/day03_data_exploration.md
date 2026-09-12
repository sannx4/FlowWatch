## Sample Profiling Results

The 100-record sample contained:

- 1 distinct country
- 1 distinct project
- 1 distinct credit
- 100 distinct reporting periods

Observed hierarchy:

Honduras
→ P007335 — WESTERN HIGHWAY
→ IDA00010
→ 100 temporal observations

This strongly indicates that API rows represent historical credit
snapshots rather than unique credits.

A preliminary candidate identifier for a snapshot is:

`(credit_number, end_of_period)`

The current sample is not sufficient to validate the full cardinality
between countries, projects, and credits because only one value of each
appears in the sample.