"""Smoke test: the Streamlit app runs without raising and shows KPIs."""

import os

from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(__file__), "..", "app", "streamlit_app.py")


def test_app_runs_without_exception():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    # default (unfiltered) view shows the KPI metrics
    labels = [m.label for m in at.metric]
    assert "Service Level (<=20s)" in labels
