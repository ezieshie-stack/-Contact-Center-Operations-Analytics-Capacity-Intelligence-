"""
Local mock of the Genesys Cloud Analytics API.

Stands in for the real `https://api.<region>.pure.cloud` so the ingestion
client (`scripts/genesys_ingest.py`) can be demonstrated end to end with no
credentials and no network. It serves the same shapes the real API uses:

  POST /oauth/token
        OAuth2 client-credentials grant -> { access_token, expires_in, ... }

  POST /api/v2/analytics/conversations/details/query
        Body: { "interval": "<start>/<end>", "paging": { "pageSize", "pageNumber" } }
        Auth: Bearer <token>
        Returns Genesys-shaped conversation details with participants ->
        sessions -> segments + metrics (durations in milliseconds), totalHits.

It sources its data from data/fact_interactions.csv so the round-trip can be
checked for parity. The first analytics call after startup returns HTTP 429
once, on purpose, to exercise the client's retry/backoff path.

Run:  python scripts/mock_genesys_server.py --port 8089
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pandas as pd

QUEUE_IDS = {
    "Intake": "q-1001-intake",
    "Crisis": "q-1002-crisis",
    "GeneralSupp": "q-1003-genservice",
    "GeneralChat": "q-1004-genchat",
}
MEDIA = {"Phone": "voice", "Chat": "message"}

_STATE = {"df": None, "throttled_once": False}


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _to_ms(seconds) -> int:
    if pd.isna(seconds):
        return 0
    return int(max(0.0, float(seconds)) * 1000)


def _row_to_conversation(row: pd.Series) -> dict:
    start = pd.to_datetime(row["interaction_datetime"]).to_pydatetime()
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    answered = int(row["answered"]) == 1
    abandoned = int(row["abandoned"]) == 1

    metrics = [
        {"name": "tWait", "value": _to_ms(row["wait_seconds"])},
        {"name": "nOffered", "value": 1},
    ]
    if answered:
        metrics += [
            {"name": "tHandle", "value": _to_ms(row["handle_seconds"])},
            {"name": "tAcw", "value": _to_ms(row["acw_seconds"])},
            {"name": "tAnswered", "value": _to_ms(row["wait_seconds"])},
            {"name": "nAnswered", "value": 1},
        ]
    if abandoned:
        metrics.append({"name": "tAbandon", "value": _to_ms(row["wait_seconds"])})

    agent_id = row["agent_id"]
    agent_session = None
    if answered and not pd.isna(agent_id):
        agent_session = {
            "participantId": f"agent-{int(agent_id)}",
            "purpose": "agent",
            "userId": str(int(agent_id)),
            "sessions": [{"sessionId": f"s-{row['interaction_id']}-a"}],
        }

    customer = {
        "participantId": f"cust-{row['interaction_id']}",
        "purpose": "customer",
        "sessions": [
            {
                "sessionId": f"s-{row['interaction_id']}-c",
                "mediaType": MEDIA.get(row["channel"], "voice"),
                "queueId": QUEUE_IDS.get(row["queue"], "q-unknown"),
                "segments": [
                    {
                        "segmentType": "interact",
                        "segmentStart": _iso(start),
                        "segmentEnd": _iso(
                            start
                            + timedelta(seconds=float(row["wait_seconds"] or 0))
                            + timedelta(seconds=float(max(0.0, row["handle_seconds"] or 0))),
                        ),
                        "wrapUpCode": None if abandoned else str(row["disposition"]),
                    }
                ],
                "metrics": metrics,
            }
        ],
    }

    participants = [customer] + ([agent_session] if agent_session else [])
    return {
        "conversationId": f"conv-{int(row['interaction_id'])}",
        "conversationStart": _iso(start),
        "originatingDirection": "inbound",
        "participants": participants,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quiet
        pass

    def _send(self, code: int, payload: dict, extra_headers: dict | None = None):
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def do_POST(self):  # noqa: N802
        if self.path.rstrip("/") == "/oauth/token":
            self._send(200, {
                "access_token": "mock-token-abc123",
                "token_type": "bearer",
                "expires_in": 86399,
            })
            return

        if self.path.startswith("/api/v2/analytics/conversations/details/query"):
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Bearer "):
                self._send(401, {"message": "Unauthorized"})
                return

            # Exercise the client's retry path exactly once.
            if not _STATE["throttled_once"]:
                _STATE["throttled_once"] = True
                self._send(429, {"message": "Rate limit exceeded"},
                           {"Retry-After": "1"})
                return

            body = self._read_body()
            paging = body.get("paging", {})
            page_size = int(paging.get("pageSize", 1000))
            page_number = int(paging.get("pageNumber", 1))

            df = _STATE["df"]
            total = len(df)
            start = (page_number - 1) * page_size
            end = min(start + page_size, total)
            page_rows = df.iloc[start:end] if start < total else df.iloc[0:0]

            conversations = [_row_to_conversation(r) for _, r in page_rows.iterrows()]
            self._send(200, {
                "conversations": conversations,
                "totalHits": total,
                "pageSize": page_size,
                "pageNumber": page_number,
                "pageCount": math.ceil(total / page_size) if page_size else 1,
            })
            return

        self._send(404, {"message": "Not found"})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8089)
    parser.add_argument("--data", default="data/fact_interactions.csv")
    args = parser.parse_args()

    _STATE["df"] = pd.read_csv(args.data)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Mock Genesys API on http://127.0.0.1:{args.port} "
          f"({len(_STATE['df']):,} conversations)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
