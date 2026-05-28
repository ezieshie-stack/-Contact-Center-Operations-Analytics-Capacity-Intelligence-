// Query: dim_queue
// Queue / channel reference with SL targets.
let
    Source = Csv.Document(
        File.Contents(DataFolder & "\dim_queue.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {
        {"queue", type text},
        {"channel", type text},
        {"target_service_level", type number},
        {"target_answer_seconds", Int64.Type}
    })
in
    Typed
