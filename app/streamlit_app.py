"""
Interactive contact-center dashboard (Streamlit).

A free, Mac-native, deployable alternative view of the same model: it loads the
pipeline's CSVs, computes the KPIs with the *same* measure definitions verified
in scripts/verify_measures.py, and presents the three pages interactively with
date / queue / channel filters.

Run locally:   streamlit run app/streamlit_app.py
Deploy free:   push to GitHub, then share via Streamlit Community Cloud
               (share.streamlit.io) pointing at app/streamlit_app.py.
"""

from __future__ import annotations

import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from verify_measures import measures  # noqa: E402  (single source of truth)

DATA = os.path.join(os.path.dirname(__file__), "..", "data")


@st.cache_data
def load():
    df = pd.read_csv(os.path.join(DATA, "fact_interactions.csv"),
                     parse_dates=["interaction_datetime"])
    sched = pd.read_csv(os.path.join(DATA, "fact_schedule.csv"))
    flags = pd.read_csv(os.path.join(DATA, "anomaly_flags.csv"), parse_dates=["day"])
    fc = pd.read_csv(os.path.join(DATA, "forecast_daily.csv"), parse_dates=["date"])
    staff = pd.read_csv(os.path.join(DATA, "staffing_requirements.csv"),
                        parse_dates=["date"])
    return df, sched, flags, fc, staff


def main():
    st.set_page_config(page_title="Contact Center Analytics", layout="wide")
    df, sched, flags, fc, staff = load()

    st.sidebar.title("Filters")
    dmin, dmax = df["interaction_datetime"].min().date(), df["interaction_datetime"].max().date()
    date_range = st.sidebar.date_input("Date range", (dmin, dmax),
                                       min_value=dmin, max_value=dmax)
    queues = st.sidebar.multiselect("Queue", sorted(df["queue"].unique()),
                                    default=sorted(df["queue"].unique()))
    channels = st.sidebar.multiselect("Channel", sorted(df["channel"].unique()),
                                      default=sorted(df["channel"].unique()))

    if isinstance(date_range, tuple) and len(date_range) == 2:
        d0, d1 = date_range
    else:
        d0, d1 = dmin, dmax
    mask = (
        (df["interaction_datetime"].dt.date >= d0)
        & (df["interaction_datetime"].dt.date <= d1)
        & (df["queue"].isin(queues))
        & (df["channel"].isin(channels))
    )
    fdf = df[mask]
    fsched = sched[(sched["date_key"] >= int(f"{d0:%Y%m%d}"))
                   & (sched["date_key"] <= int(f"{d1:%Y%m%d}"))]

    st.title("Contact Center Operations Analytics")
    if fdf.empty:
        st.warning("No interactions match the current filters.")
        return

    m = measures(fdf, fsched)

    tab1, tab2, tab3 = st.tabs(["Executive overview", "Exceptions", "Forecast & capacity"])

    with tab1:
        c = st.columns(4)
        c[0].metric("Service Level (<=20s)", f"{m['Service Level %']*100:.1f}%",
                    delta=f"{(m['Service Level %']-0.80)*100:+.1f} pp vs target")
        c[1].metric("Abandonment Rate", f"{m['Abandonment Rate %']*100:.1f}%")
        c[2].metric("AHT", f"{m['AHT (sec)']:.0f}s")
        c[3].metric("ASA", f"{m['ASA (sec)']:.0f}s")
        c2 = st.columns(4)
        c2[0].metric("Occupancy", f"{m['Occupancy %']*100:.1f}%")
        c2[1].metric("Schedule Adherence", f"{m['Schedule Adherence %']*100:.1f}%")
        c2[2].metric("Offered", f"{m['Interactions Offered']:,}")
        c2[3].metric("Answered", f"{m['Interactions Answered']:,}")

        daily = fdf.groupby(fdf["interaction_datetime"].dt.date).agg(
            within=("answered_within_threshold", "sum"),
            offered=("interaction_id", "count")).reset_index()
        daily["Service Level %"] = daily["within"] / daily["offered"] * 100
        daily = daily.rename(columns={"interaction_datetime": "date"}).set_index("date")
        st.subheader("Daily Service Level")
        st.line_chart(daily["Service Level %"])
        st.subheader("Interactions Offered by Queue")
        st.bar_chart(fdf["queue"].value_counts())

    with tab2:
        st.subheader("Abandonment vs 2σ control band")
        fl = flags[(flags["day"].dt.date >= d0) & (flags["day"].dt.date <= d1)
                   & (flags["queue"].isin(queues))]
        for q in sorted(fl["queue"].unique()):
            g = fl[fl["queue"] == q].set_index("day")
            st.caption(q)
            st.line_chart(g[["abandon_rate", "upper_band"]] * 100)
        n_anom = int(fl["is_anomaly"].sum())
        st.metric("Anomaly days flagged (filtered)", n_anom)
        dq = pd.read_csv(os.path.join(DATA, "dq_issues.csv"))
        st.metric("Data-quality violations (all data)", len(dq))
        with st.expander("Data-quality detail"):
            st.dataframe(dq, use_container_width=True)

    with tab3:
        st.subheader("Daily volume: actual vs forecast")
        chart = fc.set_index("date")[["actual", "forecast"]]
        st.line_chart(chart)
        st.subheader("Agents required (Erlang-C)")
        st.bar_chart(staff.set_index("date")["agents_required"])
        st.caption("Forecast: Holt-Winters; staffing: Erlang-C at an 80/20 service target.")


if __name__ == "__main__":
    main()
