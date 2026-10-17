# Prism platform audit — October 16, 2026

## Scope and findings

| Flow | Finding | Change and verification |
| --- | --- | --- |
| Account and profile | Supabase sign-in/sign-up UI existed; the API already verified JWTs and supported profiles. | The live sign-up form was inspected. Isolated signed-JWT tests cover profile creation and access separation. Production email confirmation was not completed because no test inbox was supplied. |
| Kalshi connection | No user credential store existed. | Each user can connect an RSA or Ed25519 API key. The API verifies balance-read access, encrypts the key ID and private key with a server-only Fernet key, and never returns the private key. Simulated tests cover encryption, isolation, deletion, and error redaction. The existing Railway Kalshi service credential successfully accessed balance and positions through the new client, read-only. |
| Basket execution | No order endpoint, preview, or trade ledger existed. | A signed-in user can preview whole-contract allocations from live quotes, then explicitly confirm short-lived, single-use, immediate-or-cancel limit orders. Results and confirmed fills are persisted; retries are idempotent. Simulated tests cover YES/NO, partial fills, reconciliation, private-basket access, and the live execution gate. No funded live order was placed. |
| Public/private basket creation | Manual save accepted anonymous submissions, which could create ownerless private baskets. | Saving now requires sign-in; publishing additionally requires a username. Owner and visibility tests pass. Anonymous AI analyses can run but do not persist baskets. |
| Search/follow/watchlist | Following and bookmarks existed, but creator search was limited to the first page and bookmark counts were absent. | Server-side username search and pagination, watchlist UI, and distinct watchlist counters were added. Signed-JWT tests cover follows, owner privacy, and watchlist counts. |
| Published basket investment metrics | No investment ledger or counters existed. | Public cards and detail views now show distinct investors and filled dollars from confirmed Kalshi fills only. Failed, unfilled, or pending orders do not count. |
| Portfolio | Basket quote history was separate from a person's actual trade history. | Account view now shows Prism basket positions, order outcomes, confirmed fills, and daily indicative history reconstructed from Kalshi candles when available. Closed or externally changed positions are marked as unvalued rather than assigned an invented settlement P/L. |
| Build entry point | AI builder was emphasized over manual selection. | Homepage and build page put manual Basket Studio first and make AI assistance secondary. |
| Diagnostics | Database, Kalshi log, pipeline traces, and cache-sync endpoints were publicly reachable. | These endpoints now require a server-only `PRISM_ADMIN_API_KEY` sent in `X-Prism-Admin-Key`; without it, they return 404. Regression tests cover this. |
| Error reporting | Several list endpoints returned HTTP 200 with empty data on database errors. | They now log the exception and return a generic 503 so the UI does not confuse an outage with an empty feed. |

## Boundaries of portfolio accounting

Prism records orders and fills initiated by Prism. It does not import every trade on the linked Kalshi account. A user can alter a position directly on Kalshi, so Prism cannot safely claim a precise realized P/L for that position without importing and reconciling those external fills and settlements. Current value and history are indicative marks for supported open positions. The UI labels unavailable valuations.

## Deployment controls

- `KALSHI_CREDENTIALS_ENCRYPTION_KEY` must remain set on the Railway API service. Losing it makes existing stored connections unreadable.
- `ENABLE_LIVE_TRADING=true` permits order submission only after a signed-in user connects credentials and explicitly confirms a valid preview. Keep it false until production smoke checks are complete.
- `PRISM_ADMIN_API_KEY` is optional; leaving it unset disables diagnostic and maintenance routes.

## Verification

- Backend: `python -m unittest discover -s tests -p 'test_*.py' -q`.
- Frontend: `npm run lint`, `npx tsc --noEmit`, `npm run build` in `prism/frontend`.
- Production smoke: verify public pages and baskets, authenticated-only API responses, diagnostics returning 404 anonymously, then inspect Railway/Vercel deployment status.
- Actual sign-up email confirmation, user-supplied Kalshi credential connection, and a funded order still require a real test account and explicit user action. Never submit a live financial order during an automated smoke test.
