# Semantic model as code (PBIP / TMDL)

This folder holds the Power BI **semantic model defined as code** in TMDL
(Tabular Model Definition Language): the star-schema tables, relationships, and
every DAX measure. It is the version-controlled source of the model the report
is built on.

> Honest note: these files were authored in this Linux environment and have
> **not** been opened in Power BI Desktop here (Desktop is Windows-only). TMDL
> is the documented Microsoft format consumed by Power BI Desktop's PBIP mode
> and by Tabular Editor 2/3 (free). Treat this as model-as-code that imports
> into those tools; expect Desktop to add `lineageTag`s and minor metadata on
> first open.

## How to use it

**Option A — Power BI Desktop (PBIP):** enable *Power BI Project (.pbip)
save format* (Preview features), then open this `ContactCenter.SemanticModel`
folder as the model of a new PBIP project and build the report against it.

**Option B — Tabular Editor (free):** open the `definition` folder's TMDL,
review/edit the model and measures, and deploy to a workspace or to a `.pbix`.

Either way, set the `DataFolder` parameter to the folder containing the CSVs
(`data/`) before refresh. The partition M mirrors `docs/power_query/*.m`.

## Layout

```
ContactCenter.SemanticModel/
  definition.pbism                 model manifest
  definition/
    database.tmdl                  compatibility level
    model.tmdl                     model-level settings
    expressions.tmdl               DataFolder parameter
    relationships.tmdl             star-schema relationships
    tables/
      fact_interactions.tmdl       fact + all KPI / anomaly measures
      fact_schedule.tmdl           adherence fact
      dim_date.tmdl                date dimension
      dim_agent.tmdl               agent -> team
      dim_queue.tmdl               queue / channel + targets
```
