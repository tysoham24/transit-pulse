"""One snapshot of NYC subway state -> data/ (parquet + latest.json + manifest).

Run by GitHub Actions every 10 minutes. Safe to run locally too.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
from google.transit import gtfs_realtime_pb2

BASE = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs"
FEEDS = {"ace": "-ace", "bdfm": "-bdfm", "g": "-g", "jz": "-jz",
         "nqrw": "-nqrw", "l": "-l", "si": "-si", "numbered": ""}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
MAX_FEED_LAG_MIN = 10
RETENTION_DAYS = 30
STOPPED_AT = 1


def fetch(feed_suffix: str) -> gtfs_realtime_pb2.FeedMessage | None:
    try:
        r = requests.get(BASE + feed_suffix, timeout=20)
        r.raise_for_status()
        msg = gtfs_realtime_pb2.FeedMessage()
        msg.ParseFromString(r.content)
        return msg
    except Exception as exc:  # transient network/feed hiccups: skip this feed
        print(f"[warn] {feed_suffix or 'numbered'}: {exc}")
        return None


def snapshot() -> pd.DataFrame:
    now = datetime.now(timezone.utc)
    rows: dict[str, dict] = {}
    for name, suffix in FEEDS.items():
        msg = fetch(suffix)
        if msg is None:
            continue
        feed_ts = datetime.fromtimestamp(msg.header.timestamp, tz=timezone.utc)
        if now - feed_ts > timedelta(minutes=MAX_FEED_LAG_MIN):
            print(f"[warn] {name}: stale header ({now - feed_ts}), skipping")
            continue
        for e in msg.entity:
            if not e.HasField("vehicle"):
                continue
            v = e.vehicle
            route = v.trip.route_id or "?"
            r = rows.setdefault(route, {"route": route, "active": 0, "stopped": 0})
            r["active"] += 1
            if v.current_status == STOPPED_AT:
                r["stopped"] += 1
    df = pd.DataFrame(rows.values())
    if df.empty:
        raise SystemExit("no data in any feed; refusing to write an empty snapshot")
    df["in_transit"] = df["active"] - df["stopped"]
    df["snapshot_ts"] = now.isoformat(timespec="seconds")
    return df.sort_values("route").reset_index(drop=True)


def write(df: pd.DataFrame) -> None:
    os.makedirs(DATA, exist_ok=True)
    day = df["snapshot_ts"].iloc[0][:10]
    path = os.path.join(DATA, f"day={day}.parquet")
    if os.path.exists(path):
        old = pd.read_parquet(path)
        # idempotency: never write the same snapshot twice
        old = old[old["snapshot_ts"] != df["snapshot_ts"].iloc[0]]
        df = pd.concat([old, df], ignore_index=True)
    df.to_parquet(path, index=False)

    # retention + manifest
    cutoff = (datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)).date().isoformat()
    files = []
    for f in sorted(os.listdir(DATA)):
        if f.startswith("day=") and f.endswith(".parquet"):
            if f[4:14] < cutoff:
                os.remove(os.path.join(DATA, f))
            else:
                files.append(f)
    with open(os.path.join(DATA, "manifest.json"), "w") as fh:
        json.dump({"files": files}, fh)

    latest = df[df["snapshot_ts"] == df["snapshot_ts"].max()]
    with open(os.path.join(DATA, "latest.json"), "w") as fh:
        json.dump({
            "ts": latest["snapshot_ts"].iloc[0],
            "total_active": int(latest["active"].sum()),
            "routes": latest[["route", "active", "stopped", "in_transit"]]
                      .to_dict(orient="records"),
        }, fh)
    print(f"wrote {len(latest)} routes -> {path}")


if __name__ == "__main__":
    write(snapshot())
