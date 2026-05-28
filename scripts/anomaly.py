"""
Threshold-based anomaly + data-quality flagging.

Two independent outputs feed the Power BI "Exceptions" page:

  data/anomaly_flags.csv   per-day KPI breaches (statistical control band)
  data/dq_issues.csv       row-level data-quality violations

Anomaly method: for each queue, compute a trailing rolling mean and standard
deviation of daily abandonment rate, and flag any day where the rate exceeds
mean + k*sigma (default k=2). This is deliberately simple and explainable so
it is defendable in an interview ("a 2-sigma statistical process-control
band on a 14-day trailing window").
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd


def daily_kpis(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["day"] = pd.to_datetime(df["interaction_datetime"]).dt.date
    grp = df.groupby(["day", "queue"])
    out = grp.agg(
        offered=("interaction_id", "count"),
        abandoned=("abandoned", "sum"),
        answered=("answered", "sum"),
        answered_within=("answered_within_threshold", "sum"),
    ).reset_index()
    out["abandon_rate"] = out["abandoned"] / out["offered"]
    out["service_level"] = np.where(
        out["answered"] > 0, out["answered_within"] / out["offered"], np.nan
    )
    out["day"] = pd.to_datetime(out["day"])
    return out.sort_values(["queue", "day"])


def flag_anomalies(kpis: pd.DataFrame, window: int = 14, k: float = 2.0) -> pd.DataFrame:
    frames = []
    for queue, g in kpis.groupby("queue"):
        g = g.sort_values("day").copy()
        roll = g["abandon_rate"].shift(1).rolling(window, min_periods=5)
        g["roll_mean"] = roll.mean()
        g["roll_std"] = roll.std()
        g["upper_band"] = g["roll_mean"] + k * g["roll_std"]
        g["is_anomaly"] = (g["abandon_rate"] > g["upper_band"]) & g["upper_band"].notna()
        frames.append(g)
    out = pd.concat(frames, ignore_index=True)
    out["day"] = out["day"].dt.date
    return out


def data_quality(df: pd.DataFrame) -> pd.DataFrame:
    issues = []
    for _, r in df.iterrows():
        problems = []
        h = r["handle_seconds"]
        if pd.isna(h):
            problems.append("handle_seconds_null")
        elif h < 0:
            problems.append("handle_seconds_negative")
        if r["answered"] == 1 and (pd.isna(r["agent_id"])):
            problems.append("answered_without_agent")
        if r["abandoned"] == 1 and r["answered"] == 1:
            problems.append("abandoned_and_answered")
        if problems:
            issues.append(
                {
                    "interaction_id": r["interaction_id"],
                    "interaction_datetime": r["interaction_datetime"],
                    "queue": r["queue"],
                    "issues": ";".join(problems),
                }
            )
    return pd.DataFrame(issues)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="infile", default="data/fact_interactions.csv")
    parser.add_argument("--out", default="data")
    parser.add_argument("--window", type=int, default=14)
    parser.add_argument("--k", type=float, default=2.0)
    args = parser.parse_args()

    df = pd.read_csv(args.infile, parse_dates=["interaction_datetime"])

    kpis = daily_kpis(df)
    flags = flag_anomalies(kpis, args.window, args.k)
    dq = data_quality(df)

    os.makedirs(args.out, exist_ok=True)
    flags.to_csv(os.path.join(args.out, "anomaly_flags.csv"), index=False)
    dq.to_csv(os.path.join(args.out, "dq_issues.csv"), index=False)

    n_anom = int(flags["is_anomaly"].sum())
    print(f"KPI rows: {len(flags):,}  |  anomaly days flagged: {n_anom}")
    print(f"Data-quality violations: {len(dq):,} rows")
    print(f"Wrote anomaly_flags.csv and dq_issues.csv to {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()
