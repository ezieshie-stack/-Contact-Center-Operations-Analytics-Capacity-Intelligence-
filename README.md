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

## Power BI build

1. Load the `data/*.csv` files (Power Query: set types, add a 15-min interval
   column, mark `dim_date` as the date table).
2. Build relationships per the data dictionary (star schema).
3. Paste the measures from `docs/dax_measures.md`.
4. Pages: **Executive overview** (KPI scorecard), **Exceptions**
   (anomaly + data-quality table with conditional formatting), **Forecast &
   capacity** (actual-vs-forecast line + agents-required from
   `staffing_requirements.csv`).

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
forecasting and Erlang-C capacity planning · reporting automation.

## Repo layout

```
scripts/    generate_data, forecast, erlang, anomaly, validate, run_pipeline
docs/       data_dictionary.md, dax_measures.md
data/        generated CSVs + metrics_report.json (created by the pipeline)
METRICS.md  validated, reproducible headline metrics
```
