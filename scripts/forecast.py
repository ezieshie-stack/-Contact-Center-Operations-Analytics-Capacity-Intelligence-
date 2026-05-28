"""
Daily call-volume forecast.

Aggregates fact_interactions to a daily series and projects forward with
Holt-Winters exponential smoothing (weekly seasonality). Writes a single
series containing both history (with fitted values) and the forecast horizon
so Power BI can chart actual vs. forecast on one axis.

    python scripts/forecast.py --horizon 21
"""

from __future__ import annotations

import argparse
import os

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing


def load_daily_volume(interactions_csv: str) -> pd.Series:
    df = pd.read_csv(interactions_csv, parse_dates=["interaction_datetime"])
    daily = (
        df.groupby(df["interaction_datetime"].dt.date)
        .size()
        .rename("offered")
    )
    daily.index = pd.to_datetime(daily.index)
    daily = daily.asfreq("D").fillna(0)
    return daily


def fit_forecast(daily: pd.Series, horizon: int) -> pd.DataFrame:
    model = ExponentialSmoothing(
        daily,
        trend="add",
        seasonal="add",
        seasonal_periods=7,
        initialization_method="estimated",
    ).fit()

    fitted = model.fittedvalues
    future = model.forecast(horizon)

    hist = pd.DataFrame(
        {
            "date": daily.index.date,
            "actual": daily.values,
            "fitted": fitted.values,
            "forecast": np.nan,
            "segment": "history",
        }
    )
    future_idx = pd.date_range(
        daily.index[-1] + pd.Timedelta(days=1), periods=horizon, freq="D"
    )
    fut = pd.DataFrame(
        {
            "date": future_idx.date,
            "actual": np.nan,
            "fitted": np.nan,
            "forecast": np.clip(future.values, 0, None),
            "segment": "forecast",
        }
    )

    out = pd.concat([hist, fut], ignore_index=True)
    # Single 'forecast' column usable by Erlang step: history uses fitted.
    out["forecast"] = out["forecast"].fillna(out["fitted"])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--horizon", type=int, default=21, help="days to forecast")
    parser.add_argument("--in", dest="infile", default="data/fact_interactions.csv")
    parser.add_argument("--out", default="data/forecast_daily.csv")
    args = parser.parse_args()

    daily = load_daily_volume(args.infile)
    result = fit_forecast(daily, args.horizon)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    result.to_csv(args.out, index=False)

    mape_base = result[result["segment"] == "history"].dropna(subset=["actual", "fitted"])
    mape = float(
        np.mean(
            np.abs(mape_base["actual"] - mape_base["fitted"])
            / mape_base["actual"].replace(0, np.nan)
        )
        * 100
    )
    print(f"History: {len(daily)} days  |  Forecast horizon: {args.horizon} days")
    print(f"In-sample MAPE: {mape:.1f}%")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
