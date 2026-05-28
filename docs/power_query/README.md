# Power Query (M) scripts

These are the actual mashup (M) queries for the model's ETL layer. In Power BI
(Desktop or Service) open the Advanced Editor for each query and paste the
matching script, or build them step-by-step from the UI — the M here documents
exactly what each query does.

A single query parameter, `DataFolder`, points at the folder holding the CSVs
(local path, OneDrive/SharePoint folder, or the output of the Genesys ingest).
Define it first (Home → Manage Parameters → New) as Text, e.g.
`C:\portfolio\contact-center\data`.

| Query | File | Role |
|---|---|---|
| `DataFolder` (parameter) | `00_parameter_DataFolder.m` | Single source path |
| `fact_interactions` | `fact_interactions.m` | Fact: type-set, 15-min interval, derived flags |
| `fact_schedule` | `fact_schedule.m` | Fact: adherence, merged with agent team |
| `dim_date` | `dim_date.m` | Date dimension (marked as date table) |
| `dim_agent` | `dim_agent.m` | Agent → team |
| `dim_queue` | `dim_queue.m` | Queue / channel reference |

Heavy/numeric work (forecast, Erlang, anomaly scoring) is done upstream in
Python; Power Query handles shaping, typing, derived columns, and the
schedule↔agent merge so the model stays a clean star schema.
