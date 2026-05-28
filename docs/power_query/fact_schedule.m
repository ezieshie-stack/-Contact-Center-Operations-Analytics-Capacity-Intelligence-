// Query: fact_schedule
// Adherence fact. Demonstrates a merge: brings the agent's team in from
// dim_agent so adherence can be sliced by team without a model hop.
let
    Source = Csv.Document(
        File.Contents(DataFolder & "\fact_schedule.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {
        {"agent_id", Int64.Type},
        {"date_key", Int64.Type},
        {"scheduled_minutes", Int64.Type},
        {"actual_minutes", Int64.Type}
    }),

    // Merge in the agent's team (left outer join on agent_id)
    Merged = Table.NestedJoin(Typed, {"agent_id"}, dim_agent, {"agent_id"},
        "agent", JoinKind.LeftOuter),
    Expanded = Table.ExpandTableColumn(Merged, "agent", {"team"}, {"team"}),

    WithAdherence = Table.AddColumn(Expanded, "adherence_pct", each
        if [scheduled_minutes] = 0 then null
        else [actual_minutes] / [scheduled_minutes], type number)
in
    WithAdherence
