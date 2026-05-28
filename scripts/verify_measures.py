"""
Measure-logic verification.

The DAX measures in pbip/ and docs/dax_measures.md can't be executed outside
Power BI here, so this independently reimplements each measure's *logic* in
pandas and checks it against the data. It does two things:

  1. Recomputes every headline measure and prints it next to the value in
     metrics_report.json (they must agree).
  2. Asserts KPI identities that must hold for any valid contact-center model
     (e.g. offered = answered + abandoned, 0 <= rates <= 1). These catch logic
     errors a circular "recompute the same formula" check would miss.

This does not prove the TMDL/DAX *loads* in Power BI (Windows-only) -- it proves
the measure definitions are arithmetically correct against the data.
"""

from __future__ import annotations

import json
import sys

import pandas as pd


def measures(df: pd.DataFrame, sched: pd.DataFrame) -> dict:
    offered = len(df)
    answered = int((df["answered"] == 1).sum())
    abandoned = int((df["abandoned"] == 1).sum())
    within = int((df["answered_within_threshold"] == 1).sum())

    ans = df[df["answered"] == 1]
    valid = ans[ans["handle_seconds"] >= 0]
    aht = float((valid["handle_seconds"] + valid["acw_seconds"]).mean())
    handle_min = float((valid["handle_seconds"] + valid["acw_seconds"]).sum() / 60)
    avail_min = float(sched["actual_minutes"].sum())
    sched_min = float(sched["scheduled_minutes"].sum())

    return {
        "Interactions Offered": offered,
        "Interactions Answered": answered,
        "Interactions Abandoned": abandoned,
        "Answered Within Threshold": within,
        "Service Level %": within / offered,
        "Abandonment Rate %": abandoned / offered,
        "AHT (sec)": aht,
        "ASA (sec)": float(df["wait_seconds"].mean()),
        "Occupancy %": handle_min / avail_min,
        "Schedule Adherence %": avail_min / sched_min,
    }


def identities(df: pd.DataFrame, m: dict) -> list[str]:
    """KPI invariants that must hold; returns list of violations."""
    bad = []
    if m["Interactions Answered"] + m["Interactions Abandoned"] != m["Interactions Offered"]:
        bad.append("offered != answered + abandoned (rows are neither/both)")
    if not (0 <= m["Service Level %"] <= 1):
        bad.append(f"service level out of [0,1]: {m['Service Level %']}")
    if not (0 <= m["Abandonment Rate %"] <= 1):
        bad.append(f"abandon rate out of [0,1]: {m['Abandonment Rate %']}")
    if m["Answered Within Threshold"] > m["Interactions Answered"]:
        bad.append("answered-within-threshold exceeds answered")
    if not (0 <= m["Occupancy %"] <= 1.5):
        bad.append(f"occupancy implausible: {m['Occupancy %']}")
    if not (0 <= m["Schedule Adherence %"] <= 1.2):
        bad.append(f"adherence implausible: {m['Schedule Adherence %']}")
    # answered-within-threshold must imply answered
    leak = ((df["answered_within_threshold"] == 1) & (df["answered"] != 1)).sum()
    if leak:
        bad.append(f"{leak} rows flagged within-threshold but not answered")
    return bad


def main() -> None:
    df = pd.read_csv("data/fact_interactions.csv")
    sched = pd.read_csv("data/fact_schedule.csv")
    report = json.load(open("data/metrics_report.json"))
    hk = report["headline_kpis"]

    m = measures(df, sched)

    print("Measure logic vs metrics_report.json:")
    checks = [
        ("Service Level %", round(m["Service Level %"] * 100, 1), hk["service_level_pct"]),
        ("Abandonment Rate %", round(m["Abandonment Rate %"] * 100, 1), hk["abandon_rate_pct"]),
        ("AHT (sec)", round(m["AHT (sec)"], 1), hk["avg_handle_time_s"]),
        ("ASA (sec)", round(m["ASA (sec)"], 1), hk["avg_speed_of_answer_s"]),
    ]
    mismatches = 0
    for name, got, expected in checks:
        ok = abs(got - expected) <= 0.1
        mismatches += (not ok)
        print(f"  {'OK ' if ok else 'XX '}{name:22s} recomputed={got}  report={expected}")

    print("\nAdditional model measures (no report baseline, shown for review):")
    for k in ("Occupancy %", "Schedule Adherence %"):
        print(f"  {k:22s} {m[k] * 100:.1f}%")

    violations = identities(df, m)
    print("\nKPI identity checks:")
    if violations:
        for v in violations:
            print(f"  XX {v}")
    else:
        print("  OK all identities hold (offered=answered+abandoned, rates in range, "
              "flags consistent)")

    if mismatches or violations:
        print(f"\nMEASURE VERIFICATION FAILED ({mismatches} mismatches, "
              f"{len(violations)} identity violations)")
        sys.exit(1)
    print("\nMeasure logic verified.")


if __name__ == "__main__":
    main()
