// Query: dim_date
// Calendar dimension. After loading, mark as the model's date table on [date].
let
    Source = Csv.Document(
        File.Contents(DataFolder & "\dim_date.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {
        {"date", type date},
        {"date_key", Int64.Type},
        {"year", Int64.Type},
        {"month", Int64.Type},
        {"month_name", type text},
        {"day", Int64.Type},
        {"day_of_week", Int64.Type},
        {"day_name", type text},
        {"is_weekend", type logical},
        {"iso_week", Int64.Type}
    })
in
    Typed
