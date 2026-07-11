# Transit Pulse

A live NYC subway operations dashboard with **zero servers and a $0/month bill**.

- **Orchestrator:** GitHub Actions (cron, every 10 minutes)
- **Warehouse:** partitioned Parquet files, committed to this repo
- **Query engine:** DuckDB-WASM, running in your browser
- **BI layer:** a static page on GitHub Pages

Live: **https://tysoham24.github.io/transit-pulse/**

```
MTA GTFS-RT ──▶ Actions cron ──▶ ingest.py ──▶ data/*.parquet + latest.json
                                                   │
                     GitHub Pages  ◀───────────────┘
                     (DuckDB-WASM queries the parquet over HTTP)
```

## Why this is interesting

Every layer of a normal data platform is here, implemented with free static
infrastructure. The scheduler is a cron workflow whose run history is public,
so the pipeline's uptime is auditable by anyone. The "warehouse" is Parquet
over HTTP with a manifest. The query engine ships to the client, so the
dashboard can run arbitrary SQL with no backend to pay for or keep alive.

It also handles the boring-but-real problems: the ingest is idempotent per
snapshot, prunes data older than 30 days to keep the repo lean, refuses to
write when the feed header is stale, and the dashboard paints instantly from
`latest.json` before DuckDB finishes loading.

## Metrics

Each 10-minute snapshot records, per route: active trains, trains stopped at
stations vs in transit, and feed freshness. The dashboard shows the live
fleet per line plus a 24-hour history for any route. (True headways need
higher-frequency polling than Actions cron allows, so this tracks the
active-fleet proxy and is honest about it.)

## Run it yourself

```bash
pip install -r ingest/requirements.txt
python ingest/ingest.py           # one snapshot into data/
python -m http.server -d .        # open localhost:8000/docs/
```

Fork it, enable Actions and Pages (main branch, `/` root), done.
