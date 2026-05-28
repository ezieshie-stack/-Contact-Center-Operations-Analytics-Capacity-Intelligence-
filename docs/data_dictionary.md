# Data Dictionary

The model is a star schema: one fact table of interactions (and a second fact
for schedule/adherence) surrounded by conformed dimensions. All tables are
emitted as CSV by `scripts/generate_data.py`.

## fact_interactions
One row per contact (call or chat).

| Column | Type | Definition |
|---|---|---|
| interaction_id | int | Surrogate key, one per contact. |
| interaction_datetime | datetime | Arrival timestamp. |
| date_key | int (YYYYMMDD) | FK to `dim_date.date_key`. |
| queue | text | FK to `dim_queue.queue` (Intake, Crisis, GeneralSupp, GeneralChat). |
| channel | text | Phone or Chat (denormalised for convenience). |
| agent_id | int / null | FK to `dim_agent.agent_id`. Null when abandoned. |
| wait_seconds | float | Time in queue before answer/abandon. |
| handle_seconds | float | Talk/handle time. 0 if abandoned. **May be <0 or null in injected data-quality rows.** |
| acw_seconds | float | After-call work time. |
| abandoned | 0/1 | Caller hung up before answer. |
| answered | 0/1 | Contact was handled by an agent. |
| answered_within_threshold | 0/1 | Answered within 20s (service-level numerator). |
| disposition | text | Resolved / Escalated / FollowUp / Transferred / Abandoned. |

## fact_schedule
One row per agent per scheduled day (drives adherence).

| Column | Type | Definition |
|---|---|---|
| agent_id | int | FK to `dim_agent.agent_id`. |
| date_key | int | FK to `dim_date.date_key`. |
| scheduled_minutes | int | Minutes the agent was scheduled. |
| actual_minutes | int | Minutes the agent was actually present/available. |

## dim_agent
| Column | Type | Definition |
|---|---|---|
| agent_id | int | Primary key. |
| agent_name | text | Display name. |
| team | text | Alpha / Bravo / Charlie / Delta. |
| speed_factor | float | Generator-internal handle-time multiplier (not for reporting). |
| hire_date | date | Tenure analysis. |

## dim_date
Standard calendar dimension keyed by `date_key` (YYYYMMDD): year, month,
month_name, day, day_of_week, day_name, is_weekend, iso_week.

## dim_queue
Reference for each queue: channel, target_service_level (0.80),
target_answer_seconds (20).

## Derived / output tables (from the analytics scripts)
- `forecast_daily.csv` — actual vs fitted vs forecast daily volume (forecast.py).
- `staffing_requirements.csv` — agents_required per forecast day (erlang.py).
- `anomaly_flags.csv` — per queue-day KPI control band + is_anomaly (anomaly.py).
- `dq_issues.csv` — row-level data-quality violations (anomaly.py).
- `ground_truth.json` — answer key of injected anomalies/DQ rows (validation only).
- `metrics_report.json` / `METRICS.md` — validated metrics (validate.py).

## Reporting standards (KPI definitions — the single source of truth)
- **Service Level** = answered within 20s / total **offered** (abandons count against SL).
- **Abandonment Rate** = abandoned / offered.
- **AHT** = mean(handle_seconds + acw_seconds) over **answered** contacts only.
- **ASA** = mean(wait_seconds) over offered.
- **Occupancy** = handle time / available (scheduled-derived) time.
- **Schedule Adherence** = actual_minutes / scheduled_minutes.
