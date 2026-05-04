Railway setup for unattended cache refresh

Goal:
- Refresh `markets_cache.json` and `events_cache.json` every day at 2:00 AM
- Make the refreshed cache visible to the live Prism backend

Why local cron is not enough:
- A laptop cron job only runs if the laptop is on and awake.
- The product reads local files from the backend container, so the refresh must happen in storage shared with that backend.

Recommended setup:
1. Create a Railway Volume.
2. Attach that same volume to:
   - the Prism API web service
   - a second Railway service configured as a Cron Job
3. Mount the volume at:
   - `/app/trading_companion/cache`
4. Set this env var on both services:
   - `TRADING_COMPANION_CACHE_DIR=/app/trading_companion/cache`
5. Set the cron service start command to:
   - `python trading_companion/sync_caches.py`
6. Set the cron schedule to:
   - `0 9 * * *`

Time note:
- Railway cron schedules use UTC.
- `0 9 * * *` is 2:00 AM in Pacific Standard Time.
- During daylight saving time, 2:00 AM Pacific is `0 10 * * *`.
- If you want a fixed local-time guarantee year-round, you need to adjust the schedule seasonally.

Relevant Railway docs:
- Volumes: https://docs.railway.com/volumes
- Cron Jobs: https://docs.railway.com/reference/cron-jobs
