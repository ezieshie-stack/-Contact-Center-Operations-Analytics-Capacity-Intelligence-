"""Measure-logic identities on the generated data (pytest entry point)."""

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from verify_measures import measures, identities  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "..", "data")


def test_kpi_identities_hold():
    df = pd.read_csv(os.path.join(DATA, "fact_interactions.csv"))
    sched = pd.read_csv(os.path.join(DATA, "fact_schedule.csv"))
    m = measures(df, sched)
    assert identities(df, m) == []


def test_service_level_in_range():
    df = pd.read_csv(os.path.join(DATA, "fact_interactions.csv"))
    sched = pd.read_csv(os.path.join(DATA, "fact_schedule.csv"))
    m = measures(df, sched)
    assert 0 <= m["Service Level %"] <= 1
    assert m["Interactions Answered"] + m["Interactions Abandoned"] == m["Interactions Offered"]
