"""
Synthetic contact-center data generator.

Produces a star-schema-ready set of CSVs for the Contact Center Operations
Analytics project:

    data/fact_interactions.csv   one row per contact (call/chat)
    data/fact_schedule.csv       one row per agent per day (adherence)
    data/dim_agent.csv           agent -> team mapping
    data/dim_date.csv            calendar dimension
    data/dim_queue.csv           queue / channel reference

The generator builds realistic structure on purpose so the downstream
Power BI model has something to show:
  - intraday volume curve (slow mornings, midday peak, evening taper)
  - weekly seasonality (weekday > weekend)
  - per-queue behaviour (crisis = longer AHT, intake = higher volume)
  - abandonment that rises with wait time
  - a handful of injected anomalies for the data-quality / anomaly page
"""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

QUEUES = {
    # queue        channel   volume_weight  base_AHT_s  aht_sigma  base_abandon
    "Intake":      ("Phone",  0.34,          300,        0.35,      0.06),
    "Crisis":      ("Phone",  0.16,          600,        0.30,      0.03),
    "GeneralSupp": ("Phone",  0.28,          240,        0.40,      0.07),
    "GeneralChat": ("Chat",   0.22,          360,        0.45,      0.04),
}

TEAMS = ["Alpha", "Bravo", "Charlie", "Delta"]
AGENTS_PER_TEAM = 10
ANSWER_THRESHOLD_S = 20            # service-level target: answered within 20s
SHIFT_START_HOUR = 7
SHIFT_END_HOUR = 21                # center operates 07:00-21:00


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _intraday_weight(hour: int) -> float:
    """Relative call-arrival weight by hour of day (bell-ish, midday peak)."""
    if hour < SHIFT_START_HOUR or hour >= SHIFT_END_HOUR:
        return 0.0
    # peak around 13:00
    return float(np.exp(-((hour - 13) ** 2) / 18.0))


def _weekday_weight(d: date) -> float:
    """Weekdays busier than weekends."""
    return 1.0 if d.weekday() < 5 else 0.45


def build_dim_agent(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    aid = 1000
    for team in TEAMS:
        for _ in range(AGENTS_PER_TEAM):
            aid += 1
            rows.append(
                {
                    "agent_id": aid,
                    "agent_name": f"Agent {aid}",
                    "team": team,
                    # per-agent skill multiplier on handle time (0.85 fast, 1.2 slow)
                    "speed_factor": float(rng.uniform(0.85, 1.2)),
                    "hire_date": (date(2021, 1, 1)
                                  + timedelta(days=int(rng.integers(0, 1400)))).isoformat(),
                }
            )
    return pd.DataFrame(rows)


def build_dim_date(start: date, end: date) -> pd.DataFrame:
    days = pd.date_range(start, end, freq="D")
    df = pd.DataFrame({"date": days})
    df["date_key"] = df["date"].dt.strftime("%Y%m%d").astype(int)
    df["year"] = df["date"].dt.year
    df["month"] = df["date"].dt.month
    df["month_name"] = df["date"].dt.strftime("%b")
    df["day"] = df["date"].dt.day
    df["day_of_week"] = df["date"].dt.dayofweek
    df["day_name"] = df["date"].dt.strftime("%a")
    df["is_weekend"] = df["day_of_week"] >= 5
    df["iso_week"] = df["date"].dt.isocalendar().week.astype(int)
    df["date"] = df["date"].dt.date
    return df


def build_dim_queue() -> pd.DataFrame:
    rows = []
    for q, (channel, weight, aht, sigma, abandon) in QUEUES.items():
        rows.append(
            {
                "queue": q,
                "channel": channel,
                "target_service_level": 0.80,
                "target_answer_seconds": ANSWER_THRESHOLD_S,
            }
        )
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Interactions
# ----------------------------------------------------------------------------

def generate_interactions(
    rng: np.random.Generator,
    agents: pd.DataFrame,
    start: date,
    end: date,
    target_rows: int,
) -> pd.DataFrame:
    days = pd.date_range(start, end, freq="D").date

    # Build a per-(day, hour) arrival weight grid, then allocate target_rows.
    grid = []
    for d in days:
        wd = _weekday_weight(d)
        for h in range(SHIFT_START_HOUR, SHIFT_END_HOUR):
            grid.append((d, h, wd * _intraday_weight(h)))
    grid_df = pd.DataFrame(grid, columns=["day", "hour", "weight"])
    grid_df["weight"] = grid_df["weight"] / grid_df["weight"].sum()
    grid_df["n"] = rng.multinomial(target_rows, grid_df["weight"].to_numpy())

    queue_names = list(QUEUES.keys())
    queue_weights = np.array([QUEUES[q][1] for q in queue_names])
    queue_weights = queue_weights / queue_weights.sum()

    agent_ids = agents["agent_id"].to_numpy()
    speed_by_agent = dict(zip(agents["agent_id"], agents["speed_factor"]))

    records = []
    interaction_id = 0
    for day, hour, _w, n in grid_df[["day", "hour", "weight", "n"]].itertuples(index=False):
        if n == 0:
            continue
        # assign queues for this bucket
        q_choices = rng.choice(len(queue_names), size=n, p=queue_weights)
        # arrival second within the hour
        secs = rng.integers(0, 3600, size=n)
        for i in range(n):
            interaction_id += 1
            q = queue_names[q_choices[i]]
            channel, _vw, base_aht, sigma, base_abandon = QUEUES[q]

            ts = datetime(day.year, day.month, day.day, hour) + timedelta(
                seconds=int(secs[i])
            )

            agent_id = int(rng.choice(agent_ids))

            # Wait time: lognormal, heavier when the hour is busy.
            load = _intraday_weight(hour)
            wait = float(rng.lognormal(mean=2.3 + 0.7 * load, sigma=0.7))
            wait = min(wait, 600.0)

            # Abandonment probability climbs with wait time.
            p_abandon = base_abandon + min(0.4, wait / 900.0)
            abandoned = int(rng.random() < p_abandon)

            if abandoned:
                handle = 0
                acw = 0
                answered = 0
                disposition = "Abandoned"
                answer_within = 0
            else:
                speed = speed_by_agent[agent_id]
                handle = float(rng.lognormal(mean=np.log(base_aht * speed), sigma=sigma))
                handle = float(np.clip(handle, 30, 4000))
                acw = float(rng.uniform(15, 90))
                answered = 1
                answer_within = int(wait <= ANSWER_THRESHOLD_S)
                disposition = rng.choice(
                    ["Resolved", "Escalated", "FollowUp", "Transferred"],
                    p=[0.70, 0.12, 0.12, 0.06],
                )

            records.append(
                {
                    "interaction_id": interaction_id,
                    "interaction_datetime": ts,
                    "date_key": int(ts.strftime("%Y%m%d")),
                    "queue": q,
                    "channel": channel,
                    "agent_id": agent_id if answered else pd.NA,
                    "wait_seconds": round(wait, 1),
                    "handle_seconds": round(handle, 1),
                    "acw_seconds": round(acw, 1),
                    "abandoned": abandoned,
                    "answered": answered,
                    "answered_within_threshold": answer_within,
                    "disposition": disposition,
                }
            )

    df = pd.DataFrame(records)
    df, ground_truth = _inject_anomalies(df, rng)
    return df, ground_truth


def _inject_anomalies(df: pd.DataFrame, rng: np.random.Generator):
    """Plant deliberate problems and return the ground truth that records them.

    The ground truth lets the validation step measure detection precision /
    recall against a known answer key, which is what makes the headline
    metrics defendable rather than self-asserted.
    """
    df = df.copy()
    ground_truth = {"anomaly_days": [], "dq_interaction_ids": []}

    # 1) Several abandonment spikes (outage-style incidents) on distinct
    #    day/queue pairs, so the answer key supports a meaningful
    #    precision/recall measurement rather than a single event.
    days = sorted(df["interaction_datetime"].dt.date.unique())
    incidents = [
        (days[len(days) // 4], "Intake", 0.55),
        (days[len(days) // 2], "Crisis", 0.50),
        (days[(2 * len(days)) // 3], "GeneralSupp", 0.60),
        (days[(5 * len(days)) // 6], "GeneralChat", 0.50),
    ]
    for spike_day, queue, frac in incidents:
        mask = (df["interaction_datetime"].dt.date == spike_day) & (df["queue"] == queue)
        if not mask.any():
            continue
        idx = df[mask].sample(frac=frac, random_state=hash((str(spike_day), queue)) % 2**31).index
        df.loc[idx, ["abandoned", "answered", "answered_within_threshold"]] = [1, 0, 0]
        df.loc[idx, "handle_seconds"] = 0
        df.loc[idx, "disposition"] = "Abandoned"
        df.loc[idx, "agent_id"] = pd.NA
        ground_truth["anomaly_days"].append(
            {"day": spike_day.isoformat(), "queue": queue, "type": "abandon_spike"}
        )

    # 2) Data-quality issues: a handful of negative / null handle times.
    bad = df.sample(n=min(40, len(df)), random_state=2).index
    df.loc[bad[:20], "handle_seconds"] = -1          # impossible value
    df.loc[bad[20:], "handle_seconds"] = pd.NA        # missing value
    ground_truth["dq_interaction_ids"] = sorted(
        int(i) for i in df.loc[bad, "interaction_id"].tolist()
    )

    return df, ground_truth


# ----------------------------------------------------------------------------
# Schedule / adherence
# ----------------------------------------------------------------------------

def generate_schedule(
    rng: np.random.Generator, agents: pd.DataFrame, start: date, end: date
) -> pd.DataFrame:
    rows = []
    for d in pd.date_range(start, end, freq="D").date:
        if d.weekday() >= 5:
            staffed = agents.sample(frac=0.4, random_state=int(d.strftime("%Y%m%d")) % 2**31)
        else:
            staffed = agents.sample(frac=0.85, random_state=int(d.strftime("%Y%m%d")) % 2**31)
        for agent_id in staffed["agent_id"]:
            scheduled = 480  # 8h shift in minutes
            # adherence centred ~92%, occasional bad days
            adherence = float(np.clip(rng.normal(0.92, 0.06), 0.5, 1.05))
            actual = round(scheduled * adherence)
            rows.append(
                {
                    "agent_id": int(agent_id),
                    "date_key": int(d.strftime("%Y%m%d")),
                    "scheduled_minutes": scheduled,
                    "actual_minutes": actual,
                }
            )
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=50_000, help="target interaction rows")
    parser.add_argument("--days", type=int, default=120, help="number of days of history")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="data", help="output directory")
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    end = date(2026, 5, 24)
    start = end - timedelta(days=args.days - 1)

    os.makedirs(args.out, exist_ok=True)

    agents = build_dim_agent(rng)
    dim_date = build_dim_date(start, end)
    dim_queue = build_dim_queue()
    interactions, ground_truth = generate_interactions(rng, agents, start, end, args.rows)
    schedule = generate_schedule(rng, agents, start, end)

    agents.to_csv(os.path.join(args.out, "dim_agent.csv"), index=False)
    dim_date.to_csv(os.path.join(args.out, "dim_date.csv"), index=False)
    dim_queue.to_csv(os.path.join(args.out, "dim_queue.csv"), index=False)
    interactions.to_csv(os.path.join(args.out, "fact_interactions.csv"), index=False)
    schedule.to_csv(os.path.join(args.out, "fact_schedule.csv"), index=False)

    import json
    with open(os.path.join(args.out, "ground_truth.json"), "w") as fh:
        json.dump(ground_truth, fh, indent=2)

    print(f"Wrote {len(interactions):,} interactions across {args.days} days "
          f"({start} -> {end})")
    print(f"  agents:   {len(agents)}")
    print(f"  schedule: {len(schedule):,} agent-days")
    print(f"  output:   {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()
