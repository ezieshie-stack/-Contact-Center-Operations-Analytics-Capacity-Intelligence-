"""
Render the three dashboard pages to PNG.

This is a Python (matplotlib) rendering of the same three pages specified for
Power BI in docs/powerbi_build_guide.md, driven by the same data and the same
measure definitions. It produces real, committable portfolio visuals on a Mac
with no Power BI:

    docs/screenshots/1_executive_overview.png
    docs/screenshots/2_exceptions.png
    docs/screenshots/3_forecast_capacity.png

Honest framing: this is a reference rendering of the dashboard design, not the
Power BI report itself. The Power BI version is built from the TMDL model +
DAX measures per the build guide; the numbers reconcile to METRICS.md.
"""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from verify_measures import measures

OUT = "docs/screenshots"
NAVY = "#1f3a5f"
ACCENT = "#2e86c1"
RED = "#c0392b"
AMBER = "#e67e22"
GREEN = "#27ae60"
GREY = "#7f8c8d"
plt.rcParams.update({"font.size": 10, "axes.titlesize": 12, "figure.dpi": 130})


def _load():
    df = pd.read_csv("data/fact_interactions.csv", parse_dates=["interaction_datetime"])
    sched = pd.read_csv("data/fact_schedule.csv")
    flags = pd.read_csv("data/anomaly_flags.csv", parse_dates=["day"])
    fc = pd.read_csv("data/forecast_daily.csv", parse_dates=["date"])
    staff = pd.read_csv("data/staffing_requirements.csv", parse_dates=["date"])
    return df, sched, flags, fc, staff


def _kpi_card(ax, label, value, target=None, good_high=True):
    ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes,
                               facecolor="white", edgecolor="#d5d8dc"))
    color = NAVY
    if target is not None:
        meets = (value >= target) if good_high else (value <= target)
        color = GREEN if meets else RED
    ax.text(0.5, 0.62, value if isinstance(value, str) else f"{value}",
            ha="center", va="center", fontsize=22, fontweight="bold",
            color=color, transform=ax.transAxes)
    ax.text(0.5, 0.22, label, ha="center", va="center", fontsize=9.5,
            color=GREY, transform=ax.transAxes)


def page_executive(df, sched):
    m = measures(df, sched)
    fig = plt.figure(figsize=(12, 7))
    fig.suptitle("Contact Center  ·  Executive Overview", fontsize=16,
                 fontweight="bold", color=NAVY, x=0.02, ha="left")

    cards = [
        ("Service Level (<=20s)", f"{m['Service Level %']*100:.1f}%", 0.80, True,
         m["Service Level %"]),
        ("Abandonment Rate", f"{m['Abandonment Rate %']*100:.1f}%", 0.08, False,
         m["Abandonment Rate %"]),
        ("AHT", f"{m['AHT (sec)']:.0f}s", None, True, None),
        ("ASA", f"{m['ASA (sec)']:.0f}s", None, True, None),
        ("Occupancy", f"{m['Occupancy %']*100:.1f}%", None, True, None),
        ("Schedule Adherence", f"{m['Schedule Adherence %']*100:.1f}%", 0.90, True,
         m["Schedule Adherence %"]),
    ]
    for i, (label, val, tgt, gh, raw) in enumerate(cards):
        ax = fig.add_axes([0.04 + (i % 3) * 0.32, 0.62 - (i // 3) * 0.18, 0.28, 0.14])
        if tgt is not None and raw is not None:
            meets = (raw >= tgt) if gh else (raw <= tgt)
            _kpi_card(ax, label, val, target=(0 if meets else 1) if False else None)
            ax.texts[0].set_color(GREEN if meets else RED)
        else:
            _kpi_card(ax, label, val)

    # SL trend
    daily = df.groupby(df["interaction_datetime"].dt.date).agg(
        within=("answered_within_threshold", "sum"), offered=("interaction_id", "count"))
    daily["sl"] = daily["within"] / daily["offered"]
    ax1 = fig.add_axes([0.06, 0.08, 0.52, 0.26])
    ax1.plot(pd.to_datetime(daily.index), daily["sl"] * 100, color=ACCENT, lw=1.4)
    ax1.axhline(80, color=RED, ls="--", lw=1, label="Target 80%")
    ax1.set_title("Daily Service Level", loc="left", color=NAVY)
    ax1.set_ylabel("%"); ax1.legend(fontsize=8); ax1.grid(alpha=0.25)

    # Offered by queue
    ax2 = fig.add_axes([0.66, 0.08, 0.30, 0.26])
    byq = df["queue"].value_counts()
    ax2.barh(byq.index[::-1], byq.values[::-1], color=NAVY)
    ax2.set_title("Interactions Offered by Queue", loc="left", color=NAVY)
    ax2.grid(axis="x", alpha=0.25)

    fig.savefig(os.path.join(OUT, "1_executive_overview.png"), bbox_inches="tight",
                facecolor="#f4f6f7")
    plt.close(fig)


def page_exceptions(df, flags):
    fig = plt.figure(figsize=(12, 7))
    fig.suptitle("Contact Center  ·  Exceptions & Data Quality", fontsize=16,
                 fontweight="bold", color=NAVY, x=0.02, ha="left")

    queues = sorted(flags["queue"].unique())
    for i, q in enumerate(queues):
        ax = fig.add_axes([0.07 + (i % 2) * 0.48, 0.56 - (i // 2) * 0.42, 0.40, 0.30])
        g = flags[flags["queue"] == q].sort_values("day")
        ax.plot(g["day"], g["abandon_rate"] * 100, color=ACCENT, lw=1.1, label="Abandon %")
        ax.plot(g["day"], g["upper_band"] * 100, color=GREY, ls="--", lw=1,
                label="2σ upper limit")
        anom = g[g["is_anomaly"] == True]  # noqa: E712
        ax.scatter(anom["day"], anom["abandon_rate"] * 100, color=RED, s=40,
                   zorder=5, label="Anomaly")
        ax.set_title(f"{q}", loc="left", color=NAVY)
        ax.grid(alpha=0.25)
        if i == 0:
            ax.legend(fontsize=7, loc="upper left")

    dq = pd.read_csv("data/dq_issues.csv")
    n_dq = len(dq)
    ax = fig.add_axes([0.07, 0.02, 0.86, 0.06]); ax.axis("off")
    ax.text(0, 0.5, f"Data-quality violations flagged: {n_dq}   "
            f"(negative/null handle time, answered-without-agent)",
            color=AMBER if n_dq else GREEN, fontsize=11, fontweight="bold")

    fig.savefig(os.path.join(OUT, "2_exceptions.png"), bbox_inches="tight",
                facecolor="#f4f6f7")
    plt.close(fig)


def page_forecast(fc, staff):
    fig = plt.figure(figsize=(12, 7))
    fig.suptitle("Contact Center  ·  Forecast & Capacity", fontsize=16,
                 fontweight="bold", color=NAVY, x=0.02, ha="left")

    ax1 = fig.add_axes([0.07, 0.40, 0.86, 0.42])
    hist = fc[fc["segment"] == "history"]
    futu = fc[fc["segment"] == "forecast"]
    ax1.plot(hist["date"], hist["actual"], color=NAVY, lw=1.2, label="Actual")
    ax1.plot(futu["date"], futu["forecast"], color=RED, lw=1.6, ls="--",
             label="Forecast (Holt-Winters)")
    ax1.set_title("Daily Volume: Actual vs Forecast", loc="left", color=NAVY)
    ax1.set_ylabel("Interactions"); ax1.legend(fontsize=8); ax1.grid(alpha=0.25)

    ax2 = fig.add_axes([0.07, 0.08, 0.86, 0.24])
    ax2.bar(staff["date"], staff["agents_required"], color=ACCENT, width=1.0)
    ax2.set_title("Agents Required (Erlang-C, 80/20 target)", loc="left", color=NAVY)
    ax2.set_ylabel("Agents"); ax2.grid(axis="y", alpha=0.25)

    fig.savefig(os.path.join(OUT, "3_forecast_capacity.png"), bbox_inches="tight",
                facecolor="#f4f6f7")
    plt.close(fig)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    df, sched, flags, fc, staff = _load()
    page_executive(df, sched)
    page_exceptions(df, flags)
    page_forecast(fc, staff)
    print(f"Wrote 3 dashboard pages to {os.path.abspath(OUT)}")


if __name__ == "__main__":
    main()
