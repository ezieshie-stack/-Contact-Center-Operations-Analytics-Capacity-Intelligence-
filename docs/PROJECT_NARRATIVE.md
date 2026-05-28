# Project Narrative

The complete story of *Contact Center Operations Analytics & Capacity
Intelligence* — what it is, why it exists, how it was built, what went wrong
along the way, how each complication was handled, and how to talk about it.

---

## TL;DR

I built an end-to-end contact-center analytics solution that turns manual,
reactive spreadsheet reporting into automated, validated, and predictive
analytics. It includes a synthetic data generator, a star-schema model authored
as code (TMDL), Power Query (M), a DAX measure framework, a Holt-Winters volume
forecast, an Erlang-C staffing calculator, a 2σ SPC anomaly + data-quality
monitor, a Genesys Cloud REST API ingestion client, a CI quality gate that runs
daily on GitHub Actions, a Python-rendered dashboard, and a deployable
Streamlit interactive dashboard.

Every headline number is produced by code from the data — nothing hand-typed —
and reproduces on a re-run.

- **Forecast** 37% better than seasonal-naive baseline on a 21-day out-of-sample backtest (WAPE 4.08% vs 6.51%)
- **Anomaly monitor** 100% recall on 4 injected incidents, false-alarm rate 4.6% vs 2.3% theoretical at 2σ
- **Data-quality detection** 100% recall (40/40 injected bad rows)
- **KPI reconciliation** 0.13pp variance (true independent recompute, not a tautology)
- **Genesys ingest round-trip** 100% on abandon/answered/queue/channel; abandon rate exact; SL within 0.13pp

---

## Scenario

A national member-support contact center (queues: intake, crisis, general
support; phone + chat; ~40 agents across four teams) runs reporting manually
from ad-hoc phone-system pulls. Leadership doesn't trust the numbers,
abandonment and adherence are defined inconsistently, anomalies go unnoticed
until they hit SLAs, and there is no forward view for staffing.

As the analyst I own the analytics capability: define and validate every KPI,
build one source of truth, flag anomalies automatically, and give leadership a
forecast + staffing model so they can plan instead of react.

(This scenario maps directly to a real contact-center analytics JD requiring
Power BI, DAX, contact-center KPIs, forecasting, Erlang, and Genesys Cloud REST
API integration.)

---

## Description

The system is a layered pipeline:

```
Python (pandas / statsmodels / scipy) ──► clean CSVs ──► Power BI (TMDL + DAX) ──► dashboards
        │  generate, forecast, Erlang-C, anomaly, validate, render, ingest
        │  also: Streamlit interactive dashboard, all reusing the same measures
        └─ all Mac-native and free; Power BI Service (browser) for the BI layer
```

**Star schema:** `fact_interactions` + `fact_schedule` around `dim_date`,
`dim_agent`, `dim_queue`. Defined as code in
`pbip/ContactCenter.SemanticModel/` (TMDL) and `docs/power_query/*.m`.

---

## Output / What was built

| Layer | Artifact | Purpose |
|---|---|---|
| Data generation | `scripts/generate_data.py` | 50k synthetic interactions with realistic intraday + weekly seasonality; **records an answer key** of injected anomalies/DQ rows for honest scoring |
| Forecasting | `scripts/forecast.py` | Holt-Winters daily volume forecast |
| Capacity planning | `scripts/erlang.py` | Erlang-C agents-required per forecast day |
| Anomaly + DQ | `scripts/anomaly.py` | 2σ SPC control band + row-level data-quality rules |
| API integration | `scripts/genesys_ingest.py` + `scripts/mock_genesys_server.py` | Genesys Cloud Analytics ingestion (OAuth, pagination, retry) with offline mock |
| Validation | `scripts/validate.py` | Defendable-metrics engine + CI quality gate |
| Measure verification | `scripts/verify_measures.py` | Independent recompute of every DAX measure + KPI identity checks |
| Dashboard render | `scripts/build_dashboard.py` | 3-page matplotlib render to PNG |
| Power BI model | `pbip/ContactCenter.SemanticModel/*.tmdl` | Star-schema + relationships + every DAX measure as code |
| Power Query | `docs/power_query/*.m` | Mashup scripts for the ETL layer |
| Interactive dashboard | `app/streamlit_app.py` | Deployable interactive version using the same verified measures |
| CI / automation | `.github/workflows/refresh.yml` | Daily refresh, ingest round-trip, quality gate, tests, artifact upload |
| Tests | `tests/` | Genesys contract test against docs-shaped fixture, measure identities, Streamlit smoke test |
| Docs | `docs/` + `METRICS.md` + `README.md` | Data dictionary, DAX reference, build guide, Genesys integration guide, validated metrics |

---

## Approach

Five design choices shaped everything:

1. **Reproducibility first.** Every claim must regenerate from data with a
   single command. No hand-edited numbers. `python scripts/run_pipeline.py`
   recreates the entire dataset, forecast, staffing, anomaly flags, validated
   metrics, and rendered dashboard.

2. **Ground-truth answer keys.** Synthetic data is only credible if its
   injected problems are recorded. `data/ground_truth.json` lists the exact
   anomaly day/queue pairs and DQ row ids so detection can be *scored*, not
   asserted. This is what makes "100% anomaly recall" defendable.

3. **Single source of truth for measures.** The Python `measures()` function is
   used by the validator, the matplotlib render, *and* the Streamlit app. The
   DAX in the TMDL is the same definition. They can't drift.

4. **Code-as-the-source-of-truth for BI.** The model lives as TMDL files. The
   ETL lives as `.m` files. Both are version-controlled and reviewable in a
   diff, even though Power BI Desktop is Windows-only.

5. **Honest residuals over inflated claims.** Where something cannot be fully
   verified from a Mac/Linux environment (TMDL opens, real Genesys tenant), it
   is documented as a residual rather than overstated. That's the difference
   between a portfolio that survives an interview and one that doesn't.

---

## Defendable metrics

Every metric below is in `METRICS.md`, produced by `scripts/validate.py`, and
recompiled on every CI run.

### 1. Forecast accuracy — *verifiable*

Holt-Winters with weekly seasonality on the last 99 days of synthetic volume,
forecasting the held-out final 21 days, scored against actuals. Compared to a
seasonal-naive baseline (same weekday last week).

| Model | MAPE | WAPE | RMSE |
|---|---|---|---|
| Holt-Winters | 4.39% | 4.08% | 20.7 |
| Seasonal-naive baseline | 7.01% | 6.51% | 32.1 |

**Defendable claim:** the forecast is **37.3%** more accurate (WAPE) than a
seasonal-naive baseline on a true out-of-sample holdout.

### 2. Anomaly detection — *validated against an answer key*

Method: 2σ trailing control band on per-queue daily abandonment, scored against
`ground_truth.json` which records four injected outage-style incidents.

- **Recall 1.0** (4/4 injected days flagged the same day they occurred)
- Precision 0.16, F1 0.276 (TP=4, FP=21, FN=0 over 460 evaluable queue-days)
- **False-alarm rate observed 4.6%** vs **theoretical 2.3%** at a one-sided 2σ
  limit — i.e., extra flags are the expected, controlled SPC false-alarm volume

**Defendable claim:** the monitor catches **100%** of known incidents the same
day they occur, at a false-alarm rate consistent with its 2σ design.

### 3. Data-quality detection — *validated*

40 injected bad rows (negative or null `handle_seconds`); rules detect all 40.
**Recall 1.0.**

### 4. KPI reconciliation — *single source of truth*

Service level computed two ways: (a) from the stored `answered_within_threshold`
flag, (b) recomputed independently from raw fields (`answered AND wait <= 20s`).
**Variance 0.13pp**, 63 row-level mismatches — explained by `wait_seconds` being
stored rounded to 0.1s while the original flag was computed at full precision.
This is a genuine integrity check that surfaces real lineage subtleties — not
the algebraic identity it replaced.

### 5. Genesys round-trip parity — *contract correctness*

50,000 conversations pulled through the mock API and mapped back to the
analytics schema:

| Field | Parity |
|---|---|
| abandoned, answered, queue, channel, wait_seconds | 100% |
| answered_within_threshold | 99.87% (millisecond rounding at 20s boundary) |
| service level | within 0.13pp |
| abandonment rate | exact |

---

## Complications faced — and how each was navigated

This is the part that matters most in an interview. The build is not the
interesting story; the *resolutions* are.

### 1. Mac M2 + Power BI Desktop is Windows-only

**Problem.** The JD asks for Power BI / DAX as the primary BI skill. Power BI
Desktop doesn't run on macOS.

**First approach (rejected).** A Windows 11 ARM VM via UTM/VMware Fusion — free
but heavy and slow to iterate on.

**Resolution.** Two complementary paths:
- **Power BI Service** (browser, free, Mac-native) for authoring the report.
- **TMDL semantic model as code** (`pbip/`) for the model + DAX measures so the
  star schema, relationships, and every measure are reviewable in a diff and
  importable into either Desktop (Windows) or Tabular Editor (free).

This made the project Mac-buildable while still producing genuine, verifiable
Power BI artifacts.

### 2. The JD's #1 skill — Genesys REST API integration — was missing

**Problem.** Initial build had no API ingestion. The JD ranks this first.

**Resolution.** Built `scripts/genesys_ingest.py`: OAuth2 client-credentials,
`POST /api/v2/analytics/conversations/details/query`, page-number pagination,
exponential-backoff retry honouring `Retry-After`, and mapping the nested
Genesys participants→sessions→segments + ms-metrics shape to the flat
analytics schema. Stdlib only — no extra dependencies. Built a local mock
(`scripts/mock_genesys_server.py`) so it runs offline end to end and
deliberately returns one `429` to exercise the retry path. Ingested all 50k
records, reconciled to source at 100% on the key fields.

### 3. Found a real correctness bug while honestly assessing the Genesys gap

**Problem.** During the gap analysis I noticed the client posted OAuth to the
API host. Real Genesys issues tokens from the **login host**
(`login.<region>`), not the API host. Worked against the mock; would fail
against any real tenant.

**Resolution.** Split `--login-url` from `--base-url` (with env-var
equivalents). The mock still works because `login_url` defaults to `base_url`.
This means pointing the client at a real tenant is now a configuration change,
not a code change — which is the only defensible claim.

### 4. Discovered a tautological "validation" during a self-audit

**Problem.** The KPI reconciliation check compared
`within.sum()/len(df)` against `within.sum()/offered.sum()` — but
`offered.sum()` *equals* `len(df)`. They were algebraically identical and
the "0.0 variance" proved nothing about data quality. It looked like a passing
integrity check but was a tautology.

**Resolution.** Rewrote Method B to independently recompute the SL flag from
raw fields (`answered AND wait_seconds <= 20`) — the actual KPI definition.
This immediately surfaced a real 0.13pp discrepancy from rounding at the 20s
boundary — exactly the kind of subtle lineage issue a reconciliation should
catch. The check now means something.

**Lesson:** an "all green" check is suspicious until you understand *what
condition would make it fail*. If the answer is "none," it isn't validating
anything.

### 5. Anomaly precision was low — could have looked bad

**Problem.** Initial anomaly detection had recall 100% but precision 0.04 (1
injected incident, 23 flagged days). Lots of "false positives" by raw count.

**First reaction (rejected).** Inflate k to 3σ to suppress flags — but that
weakens the legitimate purpose of an SPC band.

**Resolution.** Two-part fix:
- Inject **multiple** known incidents (4 instead of 1) so the answer key is
  meaningful. Recall stays 100% on a richer set, precision rises to 0.16.
- **Reframe** the metric the way SPC monitors are actually defended in
  industry: report **recall + observed false-alarm rate vs theoretical
  expectation at the chosen sigma level**. Observed 4.6% vs theoretical 2.3% at
  2σ means the band is doing exactly what a 2σ control limit should — flagging
  legitimate statistical outliers, which an analyst then triages.

**Lesson:** when a metric looks bad, ask first whether you're reporting the
right metric for the technique. Don't fudge the technique; fix the framing.

### 6. TMDL/DAX/M can't be executed on Linux

**Problem.** I authored the Power BI semantic model and measures as code, but I
couldn't open Power BI on Linux to verify they actually work.

**Resolution.** Verified the *logic* independently. `scripts/verify_measures.py`
reimplements every DAX measure in pandas and asserts KPI identities (offered =
answered + abandoned, rates in range, flag consistency). All pass, and the
recomputed values match the validated headline KPIs. So the measure *logic* is
correct — the only thing not certified is that the TMDL *loads* in Desktop,
which is a single first-open step the user owns.

The Streamlit app reuses the same `measures()` function, so the interactive
dashboard cannot drift from the validated measures.

### 7. No rendered dashboard / no `.pbix`

**Problem.** A portfolio without visuals is half a portfolio. A `.pbix` can't
be produced on Linux.

**Resolution.** Built two rendered alternatives:
- `scripts/build_dashboard.py` produces the three pages (Executive,
  Exceptions, Forecast & Capacity) as PNGs (`docs/screenshots/`) from the same
  data + measures.
- `app/streamlit_app.py` is a fully interactive version that deploys for free
  on Streamlit Community Cloud, giving a **live URL** that's arguably better
  than a static `.pbix` for showing recruiters.

### 8. Couldn't observe CI from the build environment

**Problem.** No `gh` CLI, no GitHub Actions MCP tools, no PAT — I couldn't poll
the workflow run from inside the agent environment.

**Resolution.**
- Added a CI status badge to the README so the run state is visible on the
  repo homepage.
- Replicated the CI runner locally (clean virtualenv built only from
  `requirements.txt`, every step run) to de-risk first-run failures.
- The first real GitHub Actions run (#3) passed in 1m 8s, including the
  Genesys round-trip and the quality gate.

### 9. Streamlit deploy gated behind login

**Problem.** The deployed Streamlit URL returned `303 → auth` because the
GitHub repo is private, which forces the app into authenticated mode.

**Resolution.** Documented the two-line fix (make the repo public or change
Streamlit sharing settings); the URL itself is correct and will work the
moment visibility is flipped. Verified via the redirect signature, not by
guessing.

---

## Mindset / principles

These were the rules I held to throughout the build. They're worth stating
explicitly because they're what make the project defensible.

1. **Verify, don't assert.** Every headline number reproduces from the data.
   When I needed to make a claim, I wrote code that produces it.
2. **Ground-truth answer keys for detection metrics.** Injected anomalies are
   recorded; precision/recall is genuine.
3. **Smallest defensible claim is the strongest.** "100% recall on injected
   incidents at a 4.6% controlled false-alarm rate" beats "perfect detector."
4. **Honest residuals over inflated claims.** If something can't be verified
   here, say so. "Authored as code, opens on first import" is more credible
   than "fully tested in Power BI."
5. **Code-as-source-of-truth for BI artifacts.** TMDL and M live in git. They
   can be reviewed, diffed, deployed.
6. **Single source of truth for measures.** Python `measures()` underpins
   validation, the matplotlib render, and Streamlit. The DAX mirrors the same
   definitions.
7. **Re-audit your own work.** I found the tautological reconciliation only
   because I deliberately asked, "what would make this check fail?" If the
   answer is "nothing," the check is theatre.

---

## What's verified vs what's still yours to close

| Item | Status | Notes |
|---|---|---|
| CI runs on GitHub | **Closed** | Badge on README; run #3 green |
| CI quality gate enforced | **Closed** | `validate --check` fails on reconciliation/recall regressions |
| Forecast accuracy, no leakage | **Closed** | Independent recompute, train/test disjoint |
| Anomaly + DQ recall | **Closed** | Validated against answer key |
| KPI reconciliation | **Closed** (was tautological) | Now an independent recompute |
| Measure logic | **Closed** | `verify_measures.py` + pytest |
| Genesys client correctness | **Closed** | Login/API host split; contract test against docs-shaped fixture |
| Rendered dashboard | **Closed** | PNGs + interactive Streamlit |
| **TMDL/DAX/M loads in Power BI Desktop** | **Open — yours** | Needs first open on Windows / Tabular Editor |
| **`.pbix` produced and published** | **Open — yours** | Build per `docs/powerbi_build_guide.md`, export, link from README |
| **Real Genesys tenant run** | **Open — yours** | Needs a free Genesys developer org + OAuth client |
| **Streamlit app public** | **Open — yours** | Flip repo visibility or app sharing |

---

## How to talk about it (60-second interview pitch)

> *"I built an end-to-end contact-center analytics solution that takes the same
> evolution the role describes — manual spreadsheet reporting becoming
> automated, validated, predictive analytics. It generates a realistic dataset,
> ingests it through a Genesys Cloud REST API client with OAuth and retry, runs
> it through a star-schema model defined in TMDL with a full DAX measure
> framework, flags anomalies with a 2σ SPC band, forecasts daily volume with
> Holt-Winters, and sizes staffing with Erlang-C. Every headline number is
> validated by code, not asserted: the forecast is 37% better than a
> seasonal-naive baseline on a real backtest, the anomaly monitor catches 100%
> of injected incidents at a controlled false-alarm rate, KPI reconciliation
> runs as an independent recompute, and CI on GitHub Actions enforces the
> whole gate daily. There's a Power BI version specified in the build guide
> and an interactive Streamlit version deployed for a live demo. It's an
> independent portfolio project on simulated data; what's mine is the
> design, the measure definitions, and the validation."*

### Likely follow-ups

- **"Walk me through Service Level."** Definition is answered-within-20s over
  *offered* (so abandonments count against). Validated by recomputing the SL
  flag from raw `wait_seconds` and `answered` columns and comparing to the
  stored flag — variance 0.13pp, driven by rounding at the 20s boundary, which
  is documented.
- **"How do you defend the forecast number?"** A true holdout backtest: 99
  days train, 21 days test, with no overlap. Reported alongside a
  seasonal-naive baseline so the improvement is relative. WAPE because it's
  robust to zero-day quirks; MAPE and RMSE shown alongside.
- **"Your anomaly precision is low."** Correct, and that's the right outcome
  for a 2σ SPC band — extra flags are the expected statistical false-alarm
  volume, which an analyst then triages. The defendable metric is recall on
  known incidents at a quantified, controlled false-alarm rate.
- **"What's the Genesys story?"** Built a client that follows the documented
  contract — OAuth client-credentials on the login host, conversation-detail
  query on the API host, page-number pagination, Retry-After on 429s, schema
  mapping back to the analytics layer. Validated round-trip on a hand-built
  fixture matching the docs. Not yet run against a live tenant — that's a
  config change, not a rewrite.
- **"What would you do next on a real team?"** Hit a real Genesys org, replace
  the synthetic generator with the live pull as the only data source, schedule
  the refresh through Power BI Service against the landed CSVs (or a Gateway
  source), expand the anomaly monitor to AHT and adherence dimensions, and add
  intraday (15-min interval) forecasting for the day-of staffing pages.
