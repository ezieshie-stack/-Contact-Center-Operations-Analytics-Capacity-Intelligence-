// Query: fact_interactions
// Loads the interaction fact, sets types, and adds the derived columns the
// model needs (15-minute interval key + answered-within-threshold flag).
let
    Source = Csv.Document(
        File.Contents(DataFolder & "\fact_interactions.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),

    Typed = Table.TransformColumnTypes(Promoted, {
        {"interaction_id", Int64.Type},
        {"interaction_datetime", type datetime},
        {"date_key", Int64.Type},
        {"queue", type text},
        {"channel", type text},
        {"agent_id", Int64.Type},
        {"wait_seconds", type number},
        {"handle_seconds", type number},
        {"acw_seconds", type number},
        {"abandoned", Int64.Type},
        {"answered", Int64.Type},
        {"answered_within_threshold", Int64.Type},
        {"disposition", type text}
    }),

    // 15-minute interval key (e.g. 13:00, 13:15, ...) for intraday analysis
    WithIntervalTime = Table.AddColumn(Typed, "interval_time", each
        Time.From(#datetime(1900, 1, 1, Time.Hour([interaction_datetime]),
            Number.RoundDown(Time.Minute([interaction_datetime]) / 15) * 15, 0)),
        type time),
    WithIntervalKey = Table.AddColumn(WithIntervalTime, "interval_key", each
        Time.Hour([interval_time]) * 100 + Time.Minute([interval_time]),
        Int64.Type),

    // Recompute the SL flag in-pipeline so the rule is visible/auditable in PQ
    WithSLFlag = Table.AddColumn(WithIntervalKey, "answered_within_20s", each
        if [answered] = 1 and [wait_seconds] <= 20 then 1 else 0, Int64.Type),

    // Surface obvious data-quality problems for the exceptions page
    WithDQFlag = Table.AddColumn(WithSLFlag, "dq_flag", each
        if [handle_seconds] = null then "handle_null"
        else if [handle_seconds] < 0 then "handle_negative"
        else if [answered] = 1 and [agent_id] = null then "answered_no_agent"
        else null, type text)
in
    WithDQFlag
