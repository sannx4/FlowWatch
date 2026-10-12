\# Day 14 — Ingestion CI Gate Evidence



\## Objective



Demonstrate that FlowWatch's Week-2 ingestion behavior is automatically

validated in a clean CI environment.



\## CI gates



| Gate | Responsibility |

|---|---|

| Ruff and mypy | Static code-quality and typing checks |

| Ingestion tests and coverage | Week-2 ingestion, validation and fault behavior |

| Full pytest suite | Repository regression protection |



\## Local evidence before CI



```text

Ruff                            PASS

mypy                            PASS

unit + fault tests              72 passed

full pytest                     72 passed

ingestion + validation coverage 83%

