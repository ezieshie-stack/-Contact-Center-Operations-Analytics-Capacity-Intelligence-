"""
Genesys Cloud Analytics API ingestion.

Pulls conversation detail records from the Genesys Analytics API and lands them
in the same flat `fact_interactions` schema the rest of the pipeline uses, so
the BI layer is fed by an automated API pull rather than a manual export.

Implements the parts that matter for a real integration:
  - OAuth2 client-credentials grant (POST /oauth/token)
  - POST /api/v2/analytics/conversations/details/query with an interval filter
  - cursor-free page-number pagination over the full result set
  - retry with exponential backoff, honouring Retry-After on HTTP 429 / 5xx
  - mapping the nested Genesys shape (participants -> sessions -> segments +
    millisecond metrics) down to one analytics row per conversation

Uses only the standard library (urllib) so it adds no dependencies.

Run against the local mock (default, offline):
    python scripts/mock_genesys_server.py --port 8089      # terminal 1
    python scripts/genesys_ingest.py --base-url http://127.0.0.1:8089 \
        --client-id mock --client-secret mock \
        --start 2026-01-25 --end 2026-05-24

Run against real Genesys Cloud: set --base-url to https://api.<region>.pure.cloud
and pass a real OAuth client id/secret (or the GENESYS_* env vars).
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

import pandas as pd

QUEUE_BY_ID = {
    "q-1001-intake": "Intake",
    "q-1002-crisis": "Crisis",
    "q-1003-genservice": "GeneralSupp",
    "q-1004-genchat": "GeneralChat",
}
CHANNEL_BY_MEDIA = {"voice": "Phone", "message": "Chat", "chat": "Chat"}
ANSWER_THRESHOLD_MS = 20_000


# ---------------------------------------------------------------------------
# HTTP with retry / backoff
# ---------------------------------------------------------------------------

def _request(method: str, url: str, headers: dict, body: bytes | None,
             max_retries: int = 4) -> tuple[int, dict]:
    attempt = 0
    while True:
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            status = e.code
            retry_after = e.headers.get("Retry-After")
            if status in (429, 500, 502, 503, 504) and attempt < max_retries:
                wait = float(retry_after) if retry_after else 2 ** attempt
                time.sleep(wait)
                attempt += 1
                continue
            detail = e.read().decode(errors="replace")
            raise RuntimeError(f"{method} {url} -> HTTP {status}: {detail}") from e
        except urllib.error.URLError as e:
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                attempt += 1
                continue
            raise RuntimeError(f"{method} {url} failed: {e}") from e


class GenesysClient:
    def __init__(self, base_url: str, client_id: str, client_secret: str,
                 login_url: str | None = None):
        # In production these are different hosts: tokens are issued by the
        # login host (https://login.<region>) and data is served by the API
        # host (https://api.<region>). The mock serves both on one base, so
        # login_url defaults to base_url when not given.
        self.base_url = base_url.rstrip("/")
        self.login_url = (login_url or base_url).rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: str | None = None

    def authenticate(self) -> None:
        # OAuth2 client-credentials grant against the login host.
        data = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
        import base64
        basic = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        status, payload = _request(
            "POST", f"{self.login_url}/oauth/token",
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            body=data,
        )
        self._token = payload["access_token"]

    def query_conversations(self, start: str, end: str, page_size: int = 1000):
        """Yield conversation dicts across all pages for the interval."""
        if not self._token:
            self.authenticate()
        page_number = 1
        url = f"{self.base_url}/api/v2/analytics/conversations/details/query"
        while True:
            body = json.dumps({
                "interval": f"{start}/{end}",
                "order": "asc",
                "paging": {"pageSize": page_size, "pageNumber": page_number},
            }).encode()
            _status, payload = _request(
                "POST", url,
                headers={
                    "Authorization": f"Bearer {self._token}",
                    "Content-Type": "application/json",
                },
                body=body,
            )
            conversations = payload.get("conversations", [])
            if not conversations:
                break
            for conv in conversations:
                yield conv
            total = payload.get("totalHits", 0)
            if page_number * page_size >= total:
                break
            page_number += 1


# ---------------------------------------------------------------------------
# Mapping Genesys shape -> flat analytics row
# ---------------------------------------------------------------------------

def _metric_map(session: dict) -> dict:
    return {m["name"]: m.get("value", 0) for m in session.get("metrics", [])}


def map_conversation(conv: dict) -> dict | None:
    customer = next((p for p in conv.get("participants", [])
                     if p.get("purpose") == "customer"), None)
    if not customer or not customer.get("sessions"):
        return None
    session = customer["sessions"][0]
    metrics = _metric_map(session)

    answered = "nAnswered" in metrics or "tAnswered" in metrics
    abandoned = "tAbandon" in metrics
    wait_ms = metrics.get("tWait", metrics.get("tAnswered", metrics.get("tAbandon", 0)))

    agent = next((p for p in conv.get("participants", [])
                  if p.get("purpose") == "agent"), None)
    agent_id = int(agent["userId"]) if agent and agent.get("userId") else pd.NA

    seg = (session.get("segments") or [{}])[0]
    start = pd.to_datetime(conv["conversationStart"])

    return {
        "interaction_id": int(str(conv["conversationId"]).replace("conv-", "")),
        "interaction_datetime": start.tz_localize(None) if start.tzinfo else start,
        "date_key": int(start.strftime("%Y%m%d")),
        "queue": QUEUE_BY_ID.get(session.get("queueId"), "Unknown"),
        "channel": CHANNEL_BY_MEDIA.get(session.get("mediaType"), "Phone"),
        "agent_id": agent_id,
        "wait_seconds": round(wait_ms / 1000, 1),
        "handle_seconds": round(metrics.get("tHandle", 0) / 1000, 1),
        "acw_seconds": round(metrics.get("tAcw", 0) / 1000, 1),
        "abandoned": int(abandoned),
        "answered": int(answered),
        "answered_within_threshold": int(answered and metrics.get("tAnswered", 1e9) <= ANSWER_THRESHOLD_MS),
        "disposition": seg.get("wrapUpCode") or ("Abandoned" if abandoned else "Unknown"),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("GENESYS_BASE_URL",
                                                             "http://127.0.0.1:8089"),
                        help="API host, e.g. https://api.mypurecloud.com")
    parser.add_argument("--login-url", default=os.environ.get("GENESYS_LOGIN_URL"),
                        help="login host for OAuth, e.g. https://login.mypurecloud.com "
                             "(defaults to --base-url, which is correct for the mock)")
    parser.add_argument("--client-id", default=os.environ.get("GENESYS_CLIENT_ID", "mock"))
    parser.add_argument("--client-secret", default=os.environ.get("GENESYS_CLIENT_SECRET", "mock"))
    parser.add_argument("--start", default="2026-01-25", help="interval start (YYYY-MM-DD)")
    parser.add_argument("--end", default="2026-05-24", help="interval end (YYYY-MM-DD)")
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--out", default="data/ingested_interactions.csv")
    args = parser.parse_args()

    client = GenesysClient(args.base_url, args.client_id, args.client_secret,
                           login_url=args.login_url)
    client.authenticate()
    print(f"Authenticated to {args.base_url}")

    start_iso = f"{args.start}T00:00:00.000Z"
    end_iso = f"{args.end}T23:59:59.999Z"

    rows = []
    t0 = time.time()
    for conv in client.query_conversations(start_iso, end_iso, args.page_size):
        mapped = map_conversation(conv)
        if mapped:
            rows.append(mapped)

    df = pd.DataFrame(rows).sort_values("interaction_id").reset_index(drop=True)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    df.to_csv(args.out, index=False)
    print(f"Ingested {len(df):,} conversations in {time.time()-t0:.1f}s -> {args.out}")


if __name__ == "__main__":
    main()
