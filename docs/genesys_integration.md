# Running the ingestion against a real Genesys Cloud org

`scripts/genesys_ingest.py` was validated end to end against the local mock
(`scripts/mock_genesys_server.py`). Pointing it at a real Genesys Cloud tenant
is a **configuration change, not a code change** — the client already speaks the
documented API contract:

| Concern | This client | Genesys Cloud reality |
|---|---|---|
| Auth | OAuth2 client-credentials, Basic-auth to `/oauth/token` on the login host | Same grant; `https://login.<region>` |
| Data endpoint | `POST /api/v2/analytics/conversations/details/query` on the API host | Same path; `https://api.<region>` |
| Paging | `paging.pageSize` / `paging.pageNumber`, loops on `totalHits` | Same fields |
| Throttling | retry/backoff honouring `Retry-After` on 429/5xx | Genesys returns 429 + `Retry-After` |
| Shape | participants → sessions → segments + ms metrics (`tWait`, `tHandle`, `tAnswered`, `tAbandon`, …) | Matches the Analytics Detail schema |

> Honest scope: this has been run against the mock, not a production tenant. The
> contract matches the public Genesys API docs, but a real run may still need
> small tweaks (exact metric names per media type, conversation-vs-session
> granularity, date-window page caps).

**Contract test:** `tests/test_genesys_contract.py` runs the mapper against
`tests/fixtures/genesys_conversation_detail.json` — a fixture hand-built to the
documented conversation-detail shape, independent of the mock server. It covers
an answered voice call, an abandoned chat, and the 20s threshold boundary. This
is the strongest confidence available short of a live tenant.

## Steps (free Genesys Cloud developer org)

1. Create a developer/trial org (developer.genesys.cloud).
2. **Admin → Integrations → OAuth → Add Client**, grant type *Client
   Credentials*. Note the Client ID / Secret.
3. Give the client a role with `analytics:conversationDetail:view`.
4. Find your region hosts (e.g. US East: `api.mypurecloud.com` /
   `login.mypurecloud.com`; EU: `api.mypurecloud.ie` / `login.mypurecloud.ie`).
5. Run:

```bash
export GENESYS_BASE_URL=https://api.mypurecloud.com
export GENESYS_LOGIN_URL=https://login.mypurecloud.com
export GENESYS_CLIENT_ID=<client-id>
export GENESYS_CLIENT_SECRET=<client-secret>

python scripts/genesys_ingest.py --start 2026-05-01 --end 2026-05-07
```

The output `data/ingested_interactions.csv` lands in the same schema the rest of
the pipeline and Power BI model consume, so nothing downstream changes.
