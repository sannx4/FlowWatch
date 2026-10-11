\# Day 7 — End-to-End Lineage Demonstration



\## Objective



Demonstrate that one canonical PostgreSQL temporal snapshot can be

traced back to the corresponding raw World Bank source record and to

the exact source-response bytes preserved in MongoDB.



\---



\## Source Retrieval



The Day-7 sample was fetched directly from the World Bank source API.



Observed source metadata:



\- API total record count: `1612290`

\- selected records: `100`

\- first inspected credit: `IDA00010`

\- first inspected reporting period: `30-Jun-2022`



The exact response bytes were retained before transformation.



\---



\## Vertical-Slice Run



Run identifier:



`cc23e4df-3d63-5eda-b4a1-fffd46eccbfd`



Whole-response SHA-256:



`51a8ce3625d459d54beebf034f28b6aaddbc17dd6af66bde815ae10d227e4de0`



Observed canonical counts:



\- regions: 1

\- countries: 1

\- projects: 1

\- credits: 1

\- credit\_snapshots: 100



Observed raw MongoDB counts:



\- day07\_raw\_records: 100

\- day07\_raw\_payloads: 1



The first 100 API rows therefore represent 100 temporal observations

of the same credit rather than 100 independent credits.



\---



\## Traced Snapshot



The lineage proof selected:



\- credit\_number: `IDA00010`

\- end\_of\_period: `2011-04-30`

\- source\_record\_key: `IDA00010|30-Apr-2011`

\- ingestion\_run\_id:

&#x20; `cc23e4df-3d63-5eda-b4a1-fffd46eccbfd`



PostgreSQL source checksum:



`9da721e80e035de65cac5eeb0dabc2118cbdb7ee4044066bfbc5cfcdedcad767`



MongoDB source checksum:



`9da721e80e035de65cac5eeb0dabc2118cbdb7ee4044066bfbc5cfcdedcad767`



The checksums are identical.



\---



\## Proven Lineage Chain



```text

World Bank API response

&#x20;       |

&#x20;       | exact bytes

&#x20;       v

MongoDB day07\_raw\_payloads

&#x20;       |

&#x20;       | source\_file\_checksum

&#x20;       v

MongoDB day07\_raw\_records

&#x20;       |

&#x20;       | ingestion\_run\_id

&#x20;       | source\_record\_key

&#x20;       | source\_checksum

&#x20;       v

PostgreSQL credit\_snapshots
