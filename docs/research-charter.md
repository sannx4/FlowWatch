\# FlowWatch Focused Research Charter



\## 1. Research Problem



FlowWatch studies multi-horizon uncertainty calibration under temporal

distribution shift when feedback arrives at different times for

different forecast horizons.



Suppose a forecast is issued at time t for:



\- 3 months;

\- 6 months;

\- 12 months.



The 3-month outcome becomes observable before the 6-month outcome, and

the 6-month outcome becomes observable before the 12-month outcome.



This creates an information-age asymmetry.



At a new forecast origin, the most recent 12-month residual may be much

older than already-matured 3-month or 6-month residuals.



FlowWatch investigates whether those fresher short-horizon residuals

contain useful information about unresolved long-horizon uncertainty.



The PostgreSQL, MongoDB, orchestration, lineage, observability and MLOps

components exist to make this experiment reproducible and temporally

valid. They are not themselves the principal scientific novelty.



\---



\## 2. M1 — Point Forecasting



The primary predictive task forecasts cumulative disbursement behaviour.



Primary horizons:



\- 3 months

\- 6 months

\- 12 months



For a credit i and forecast origin t:



```text

information available by t

&#x20;       ↓

point forecasting model

&#x20;       ↓

ŷ(i,t,3)

ŷ(i,t,6)

ŷ(i,t,12)
