# Power BI build guide

Step-by-step to assemble the report from the artifacts in this repo. Works in
**Power BI Service** (browser, Mac-friendly) or **Power BI Desktop** (Windows /
VM). Estimated 2-3 hours.

## 0. Prerequisites
- Run `python scripts/run_pipeline.py` so `data/*.csv` exist.
- (Optional) Run the Genesys ingest to produce `data/ingested_interactions.csv`
  and use that as the fact source instead, to show the API-fed path.

## 1. Load the data
Service: *New report → Add data → Excel/CSV*, upload each CSV.
Desktop/PBIP: open the `pbip/ContactCenter.SemanticModel` folder (it already
encodes the model below); set the `DataFolder` parameter to your `data/` path
and refresh. If building from scratch, paste the M from `docs/power_query/`.

## 2. Model (star schema)
Create these relationships (single-direction, dim filters fact):

| From (fact) | To (dim) |
|---|---|
| fact_interactions[date_key] | dim_date[date_key] |
| fact_interactions[agent_id] | dim_agent[agent_id] |
| fact_interactions[queue] | dim_queue[queue] |
| fact_schedule[date_key] | dim_date[date_key] |
| fact_schedule[agent_id] | dim_agent[agent_id] |

Mark `dim_date` as the date table (on `[date]`). Hide key columns from report
view. (All of this is already declared in `relationships.tmdl`.)

## 3. Measures
Paste every measure from `docs/dax_measures.md` (or, in Desktop/PBIP, they are
already on `fact_interactions` / `fact_schedule`). Confirm `Service Level %`
matches `METRICS.md` (≈56%) — that proves the model reconciles to the validated
numbers.

## 4. Pages

**Page 1 — Executive overview**
- KPI cards: `Service Level %`, `Abandonment Rate %`, `AHT (sec)`, `ASA (sec)`,
  `Occupancy %`, `Schedule Adherence %`.
- Line: `Service Level %` by `dim_date[date]` with a constant line at 0.80.
- Bar: `Interactions Offered` by `queue`; donut by `channel`.

**Page 2 — Exceptions (anomaly + data quality)**
- Matrix: `dim_date[date]` × `queue` with `Abandonment Rate %`,
  `Abandon Upper Control Limit`, `Is Anomaly Day`.
- Conditional formatting: red fill where `Is Anomaly Day = 1`.
- Card + table for `Data Quality Issues` (drill to `dq_flag`).

**Page 3 — Forecast & capacity**
- Load `forecast_daily.csv` and `staffing_requirements.csv` as tables.
- Line: `actual` vs `forecast` by date (history + horizon).
- Column: `agents_required` by date; card for next-7-day peak staffing.

## 5. Publish & portfolio
- Service: *Publish*; set **scheduled refresh** on the dataset (point at the
  CSV folder / OneDrive). Desktop: *File → Export → PDF*.
- Export PDF/PNG of each page and commit under `docs/screenshots/`.
- Link the published report (or PDF) from the top of `README.md`.

## Reconciliation check (do this, it's your credibility)
Open `METRICS.md`, then confirm the dashboard's Service Level, Abandonment Rate,
and AHT match. If they match, every claim in the README is demonstrably true in
the live report — which is the whole point.
