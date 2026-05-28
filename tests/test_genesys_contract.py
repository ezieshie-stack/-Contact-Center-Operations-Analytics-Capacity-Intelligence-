"""
Contract test for the Genesys ingestion mapper.

Validates `map_conversation` against a fixture hand-built to the *documented*
Genesys Cloud Analytics conversation-detail shape -- independent of our mock
server. This is the strongest confidence we can get short of a live tenant: if
the public API contract is what the docs say, the mapper handles it.

Covers both an answered voice conversation and an abandoned chat, exercising:
  - queueId -> queue name mapping
  - mediaType -> channel mapping
  - millisecond metrics -> seconds
  - answered / abandoned / answered-within-threshold derivation
  - agent userId extraction and wrap-up -> disposition
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from genesys_ingest import map_conversation  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures",
                       "genesys_conversation_detail.json")


def _load():
    with open(FIXTURE) as fh:
        return json.load(fh)["conversations"]


def test_answered_voice_conversation():
    conv = _load()[0]
    row = map_conversation(conv)
    assert row["interaction_id"] == 5001
    assert row["queue"] == "Intake"
    assert row["channel"] == "Phone"
    assert row["agent_id"] == 1010
    assert row["wait_seconds"] == 12.0
    assert row["handle_seconds"] == 300.0
    assert row["acw_seconds"] == 40.0
    assert row["answered"] == 1
    assert row["abandoned"] == 0
    assert row["answered_within_threshold"] == 1   # tAnswered 12000ms <= 20000ms
    assert row["disposition"] == "Resolved"


def test_abandoned_chat_conversation():
    conv = _load()[1]
    row = map_conversation(conv)
    assert row["interaction_id"] == 5002
    assert row["queue"] == "GeneralChat"
    assert row["channel"] == "Chat"
    assert row["answered"] == 0
    assert row["abandoned"] == 1
    assert row["answered_within_threshold"] == 0
    assert row["wait_seconds"] == 45.0
    assert row["disposition"] == "Abandoned"
    # abandoned conversations have no agent
    import pandas as pd
    assert pd.isna(row["agent_id"])


def test_threshold_boundary():
    """A 21s answer must NOT count as within the 20s threshold."""
    conv = _load()[0]
    conv["participants"][0]["sessions"][0]["metrics"] = [
        {"name": "tWait", "value": 21000},
        {"name": "tAnswered", "value": 21000},
        {"name": "tHandle", "value": 100000},
        {"name": "nAnswered", "value": 1},
    ]
    row = map_conversation(conv)
    assert row["answered"] == 1
    assert row["answered_within_threshold"] == 0


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
