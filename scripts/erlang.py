"""
Erlang-C staffing calculator.

Given a call volume, average handle time, and a service-level target, compute
the number of agents required. Used by the capacity-planning page.

Run standalone to produce data/staffing_requirements.csv from the forecast:

    python scripts/erlang.py
"""

from __future__ import annotations

import math
import os

import pandas as pd


def erlang_c(agents: int, traffic_intensity: float) -> float:
    """Probability that an arriving call has to wait (Erlang-C formula).

    agents              number of agents (servers), N
    traffic_intensity   offered load in Erlangs, A = lambda * AHT
    """
    if agents <= traffic_intensity:
        return 1.0  # system is overloaded, every call waits

    # sum_{k=0}^{N-1} A^k / k!
    summation = sum(traffic_intensity**k / math.factorial(k) for k in range(agents))
    last_term = traffic_intensity**agents / math.factorial(agents)
    erlang_b = last_term / (summation + last_term)
    rho = traffic_intensity / agents
    return erlang_b / (1 - rho * (1 - erlang_b))


def service_level(
    agents: int,
    calls: float,
    aht_seconds: float,
    target_seconds: float,
    period_seconds: float = 3600.0,
) -> float:
    """Fraction of calls answered within target_seconds for a given staffing."""
    arrival_rate = calls / period_seconds            # calls per second
    traffic = arrival_rate * aht_seconds             # Erlangs
    if agents <= traffic:
        return 0.0
    pw = erlang_c(agents, traffic)
    exponent = -(agents - traffic) * (target_seconds / aht_seconds)
    return 1 - pw * math.exp(exponent)


def agents_required(
    calls: float,
    aht_seconds: float,
    target_sl: float = 0.80,
    target_seconds: float = 20.0,
    period_seconds: float = 3600.0,
    max_agents: int = 500,
) -> int:
    """Smallest agent count that meets the service-level target."""
    if calls <= 0:
        return 0
    traffic = (calls / period_seconds) * aht_seconds
    n = max(1, math.floor(traffic))
    while n < max_agents:
        if service_level(n, calls, aht_seconds, target_seconds, period_seconds) >= target_sl:
            return n
        n += 1
    return max_agents


def occupancy(calls: float, aht_seconds: float, agents: int,
              period_seconds: float = 3600.0) -> float:
    if agents <= 0:
        return 0.0
    traffic = (calls / period_seconds) * aht_seconds
    return min(traffic / agents, 1.0)


def build_from_forecast(
    forecast_csv: str = "data/forecast_daily.csv",
    out_csv: str = "data/staffing_requirements.csv",
    aht_seconds: float = 300.0,
    operating_hours: float = 14.0,
    target_sl: float = 0.80,
    target_seconds: float = 20.0,
) -> pd.DataFrame:
    """Translate a daily volume forecast into daily agent requirements.

    Spreads forecast volume across the operating day and sizes for the
    busy-hour load (volume concentrated in the peak hour ~ 1.6x average).
    """
    fc = pd.read_csv(forecast_csv)
    rows = []
    for _, r in fc.iterrows():
        daily_calls = max(0.0, float(r["forecast"]))
        avg_hourly = daily_calls / operating_hours
        busy_hour_calls = avg_hourly * 1.6
        n = agents_required(busy_hour_calls, aht_seconds, target_sl, target_seconds)
        rows.append(
            {
                "date": r["date"],
                "forecast_calls": round(daily_calls, 1),
                "busy_hour_calls": round(busy_hour_calls, 1),
                "aht_seconds": aht_seconds,
                "agents_required": n,
                "modeled_occupancy": round(occupancy(busy_hour_calls, aht_seconds, n), 3),
                "target_service_level": target_sl,
            }
        )
    out = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    out.to_csv(out_csv, index=False)
    return out


def main() -> None:
    # Quick sanity demo
    demo_calls, demo_aht = 100, 300
    n = agents_required(demo_calls, demo_aht)
    sl = service_level(n, demo_calls, demo_aht, 20.0)
    print(f"Demo: {demo_calls} calls/hr @ {demo_aht}s AHT -> "
          f"{n} agents, SL={sl:.1%}, occ={occupancy(demo_calls, demo_aht, n):.1%}")

    if os.path.exists("data/forecast_daily.csv"):
        out = build_from_forecast()
        print(f"Wrote staffing requirements for {len(out)} forecast days "
              f"-> data/staffing_requirements.csv")
        print(out.head().to_string(index=False))
    else:
        print("No data/forecast_daily.csv found; run scripts/forecast.py first.")


if __name__ == "__main__":
    main()
