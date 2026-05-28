# DAX Measures

Paste these into Power BI (Desktop or Service) once the model is built with the
relationships in `data_dictionary.md`. Each KPI matches the validated Python
definition exactly, so the dashboard reconciles to `METRICS.md`.

## Base / helper measures

```dax
Interactions Offered = COUNTROWS ( fact_interactions )

Interactions Answered =
CALCULATE ( [Interactions Offered], fact_interactions[answered] = 1 )

Interactions Abandoned =
CALCULATE ( [Interactions Offered], fact_interactions[abandoned] = 1 )

Answered Within Threshold =
CALCULATE ( [Interactions Offered], fact_interactions[answered_within_threshold] = 1 )
```

## Headline KPIs

```dax
Service Level % =
DIVIDE ( [Answered Within Threshold], [Interactions Offered] )

Abandonment Rate % =
DIVIDE ( [Interactions Abandoned], [Interactions Offered] )

AHT (sec) =
CALCULATE (
    AVERAGEX (
        fact_interactions,
        fact_interactions[handle_seconds] + fact_interactions[acw_seconds]
    ),
    fact_interactions[answered] = 1,
    fact_interactions[handle_seconds] >= 0   -- exclude injected bad rows
)

ASA (sec) =
AVERAGE ( fact_interactions[wait_seconds] )
```

## Occupancy & adherence (use fact_schedule)

```dax
Handle Minutes =
CALCULATE (
    SUMX (
        fact_interactions,
        ( fact_interactions[handle_seconds] + fact_interactions[acw_seconds] ) / 60
    ),
    fact_interactions[answered] = 1,
    fact_interactions[handle_seconds] >= 0
)

Available Minutes = SUM ( fact_schedule[actual_minutes] )

Occupancy % = DIVIDE ( [Handle Minutes], [Available Minutes] )

Scheduled Minutes = SUM ( fact_schedule[scheduled_minutes] )

Schedule Adherence % = DIVIDE ( [Available Minutes], [Scheduled Minutes] )
```

## Anomaly / data-quality (control band, mirrors anomaly.py)

```dax
-- 14-day trailing mean of the daily abandonment rate (prior days only)
Abandon Rate Roll Mean =
VAR CurrentDate = MAX ( dim_date[date] )
RETURN
CALCULATE (
    AVERAGEX (
        VALUES ( dim_date[date] ),
        [Abandonment Rate %]
    ),
    DATESINPERIOD ( dim_date[date], CurrentDate - 1, -14, DAY )
)

Abandon Rate Roll StdDev =
VAR CurrentDate = MAX ( dim_date[date] )
RETURN
CALCULATE (
    STDEVX.S ( VALUES ( dim_date[date] ), [Abandonment Rate %] ),
    DATESINPERIOD ( dim_date[date], CurrentDate - 1, -14, DAY )
)

Abandon Upper Control Limit =
[Abandon Rate Roll Mean] + 2 * [Abandon Rate Roll StdDev]

Is Anomaly Day =
IF (
    NOT ISBLANK ( [Abandon Upper Control Limit] )
        && [Abandonment Rate %] > [Abandon Upper Control Limit],
    1, 0
)

Data Quality Issues =
CALCULATE (
    COUNTROWS ( fact_interactions ),
    FILTER (
        fact_interactions,
        fact_interactions[handle_seconds] < 0
            || ISBLANK ( fact_interactions[handle_seconds] )
            || ( fact_interactions[answered] = 1 && ISBLANK ( fact_interactions[agent_id] ) )
    )
)
```

## Forecast variance (after loading forecast_daily.csv as a table)

```dax
Forecast Calls = SUM ( forecast_daily[forecast] )
Actual Calls   = SUM ( forecast_daily[actual] )

Forecast vs Actual Variance =
DIVIDE ( [Actual Calls] - [Forecast Calls], [Forecast Calls] )
```

## Conditional formatting tip
On the exceptions table, format rows where `[Is Anomaly Day] = 1` (red fill) and
where `[Data Quality Issues] > 0` (amber). On the executive page, color
`Service Level %` against the 0.80 target with a KPI/gauge visual.
