// Query: dim_agent
// Agent dimension. speed_factor is a generator artifact; hide it from report view.
let
    Source = Csv.Document(
        File.Contents(DataFolder & "\dim_agent.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {
        {"agent_id", Int64.Type},
        {"agent_name", type text},
        {"team", type text},
        {"speed_factor", type number},
        {"hire_date", type date}
    }),
    Removed = Table.RemoveColumns(Typed, {"speed_factor"})
in
    Removed
