# Contact Center Operations Analytics & Capacity Intelligence

An end-to-end analytics solution for a member-support contact center: a data
pipeline, a star-schema model, a DAX KPI framework, an anomaly / data-quality
monitor, and a volume forecast with Erlang-C staffing. It turns manual, reactive
spreadsheet reporting into **automated, validated, and predictive** analytics.

> Independent portfolio project on **simulated** contact-center data. The
> scenario is realistic; the build, the metrics, and the validation are
> genuinely mine and fully reproducible.

## Scenario

A national member-support contact center (queues: intake, crisis, general
support; phone + chat; ~40 agents across four teams) runs reporting manually
from ad-hoc phone-system pulls. Leadership doesn't trust the numbers,
abandonment and adherence are defined inconsistently, anomalies go unnoticed
until they hit SLAs, and there is no forward view for staffing. As the analyst I
own the analytics capability: define and validate every KPI, build one source of
truth, flag anomalies automatically, and give leadership a forecast + staffing
model so they can plan instead of react.

## Defendable metrics

Every number is produced by `scripts/validate.py` from the data — nothing is
hand-typed — and reproduces on a re-run. Full detail in [`METRICS.md`](METRICS.md).

| Capability | Metric | Result | Why it's defendable |
|---|---|---|---|
| **Forecasting** | Volume forecast WAPE vs seasonal-naive baseline, true out-of-sample | **37% more accurate** (WAPE 4.1% vs 6.5%) | 21-day holdout backtest; scored against actuals and a baseline |
| **Anomaly detection** | Recall on injected incidents | **100%** (4/4), false-alarm rate 4.6% vs 2.3% theoretical | Scored against a recorded answer key; SPC false-alarm rate quantified |
| **Data quality** | Recall on injected bad rows | **100%** (40/40) | Validation rules checked against the known injected set |
| **Trust / SSOT** | KPI reconciliation variance | **0.0** | Service level computed two independent ways must agree |
| **REST API integration** | ETL round-trip parity vs source | **100%** abandon/answered/queue/channel; abandon rate exact, SL within 0.13pp | Full pull through a Genesys-shaped API, mapped back and reconciled |

These are the claims to make in an interview — each comes with a method and a
reproducible result, not an assertion.

## Architecture

```
Python (pandas/statsmodels/scipy) ──► clean CSVs ──► Power BI (model + DAX) ──► dashboards
        │  generate, forecast, Erlang-C, anomaly, validate
        └─ all Mac-native and free; Power BI Service (browser) for the BI layer
```

Star schema: `fact_interactions` + `fact_schedule` around `dim_date`,
`dim_agent`, `dim_queue`. See [`docs/data_dictionary.md`](docs/data_dictionary.md)
and [`docs/dax_measures.md`](docs/dax_measures.md).

## Quick start

```bash
pip install -r requirements.txt
python scripts/run_pipeline.py        # generate → forecast → erlang → anomaly → validate
```

Outputs land in `data/` (CSVs for Power BI) and `METRICS.md` (validated numbers).
Individual steps:

```bash
python scripts/generate_data.py --rows 50000 --days 120
python scripts/forecast.py --horizon 21
python scripts/erlang.py
python scripts/anomaly.py --k 2.0 --window 14
python scripts/validate.py
```

## REST API integration (Genesys Cloud)

The BI layer can be fed by an automated API pull instead of a manual export.
`scripts/genesys_ingest.py` implements a real-shaped Genesys Cloud Analytics
integration:

- OAuth2 **client-credentials** grant (`POST /oauth/token`)
- `POST /api/v2/analytics/conversations/details/query` with an interval filter
- **page-number pagination** over the full result set
- **retry with exponential backoff**, honouring `Retry-After` on 429 / 5xx
- mapping the nested Genesys shape (participants → sessions → segments +
  millisecond metrics) down to the flat `fact_interactions` schema

It uses only the Python standard library (no extra deps). A local mock of the
API (`scripts/mock_genesys_server.py`) lets the whole thing run offline with no
credentials, and deliberately returns one `429` so the retry path is exercised.

```bash
python scripts/mock_genesys_server.py --port 8089 &        # mock API
python scripts/genesys_ingest.py --base-url http://127.0.0.1:8089 \
    --client-id mock --client-secret mock \
    --start 2026-01-25 --end 2026-05-24                     # -> data/ingested_interactions.csv
```

Against real Genesys Cloud, point `--base-url` at `https://api.<region>.pure.cloud`
and pass a real OAuth client id/secret (or set `GENESYS_BASE_URL`,
`GENESYS_CLIENT_ID`, `GENESYS_CLIENT_SECRET`). The pull reconciles to the source
at 100% on abandon/answered/queue/channel and exact on abandonment rate.

### Scheduled / automated refresh
- The ingest script is idempotent per interval and cron / Task-Scheduler
  friendly (daily incremental pull by date interval).
- In Power BI Service, configure scheduled refresh on the published dataset
  pointed at the landed CSVs (or a folder/Gateway source).

## Power BI build

The model is version-controlled as code and the ETL is documented as real M:

- **Semantic model as code (TMDL):** `pbip/ContactCenter.SemanticModel/` — the
  star-schema tables, relationships, and every DAX measure, deployable via
  Power BI Desktop (PBIP) or Tabular Editor. (Authored here; opened/validated in
  Desktop, which is Windows-only — see `pbip/README.md`.)
- **Power Query (M):** `docs/power_query/*.m` — the actual mashup queries
  (type-setting, 15-min interval, derived flags, schedule↔agent merge).
- **Step-by-step assembly:** `docs/powerbi_build_guide.md` (Service or Desktop),
  including the reconciliation check against `METRICS.md`.

Pages: **Executive overview** (KPI scorecard), **Exceptions** (anomaly +
data-quality with conditional formatting), **Forecast & capacity**
(actual-vs-forecast + agents-required from `staffing_requirements.csv`).

## Automation & quality gate

`.github/workflows/refresh.yml` runs daily (and on push): it regenerates the
data, recomputes forecast/Erlang/anomaly outputs, runs the Genesys ingest
round-trip, and enforces a **data-quality gate** (`python scripts/validate.py
--check` fails the build if reconciliation drifts or detection recall drops).
Refreshed CSVs + `METRICS.md` are published as build artifacts; Power BI Service
scheduled refresh consumes the landed CSVs.

## Tooling (all free, Mac M2-compatible)

- **Python** (pandas, statsmodels, scipy) — data generation, forecast, Erlang-C,
  anomaly flags, validation. Native on Apple Silicon.
- **Power BI Service** (app.powerbi.com, browser) — model, DAX, dashboards. The
  Power BI + DAX claim without a Windows VM. (Power BI Desktop is Windows-only;
  use a free Windows 11 ARM VM via UTM/VMware Fusion only if you want full
  Desktop Power Query.)
- **VS Code**, **GitHub** — editing and hosting.

## Skills this demonstrates

Power BI (DAX, data modeling, dashboard design) · contact-center KPIs (service
level, abandonment, AHT, ASA, occupancy, adherence) · data integrity & anomaly
detection with a documented data dictionary and reporting standards ·
forecasting and Erlang-C capacity planning · **Genesys Cloud REST API
integration** (OAuth, pagination, retry, schema mapping) · reporting automation.

## Repo layout

```
scripts/    generate_data, forecast, erlang, anomaly, validate, run_pipeline,
            genesys_ingest, mock_genesys_server
docs/       data_dictionary.md, dax_measures.md, powerbi_build_guide.md,
            power_query/*.m
pbip/       ContactCenter.SemanticModel (model + measures as TMDL)
.github/    workflows/refresh.yml (scheduled refresh + quality gate)
data/        generated CSVs + metrics_report.json (created by the pipeline)
METRICS.md  validated, reproducible headline metrics
```
