"""
Fetch daily oracle bond prices from ClickHouse and save JSON under json/oracle-{asset}/.

Prerequisites:
  1. ./scripts/clickhouse_access.sh   (or kubectl port-forward to ClickHouse 8123)
  2. ClickHouse reachable at localhost:8123

Usage:
  python daily_oracle_prices.py              # all configured assets
  python daily_oracle_prices.py tesouro ktb  # subset
"""

import argparse
import base64
import json
from collections import defaultdict
from pathlib import Path

from src.clickhouse_client import ClickHouseClient
from src.oracle_payload import daily_record_from_row

PROJECT_ROOT = Path(__file__).resolve().parent

ORACLE_FEEDS: dict[str, dict[str, str]] = {
    "tesouro": {
        "subject": "ch.mw.etherfuse.status.TESOURO-USDC",
        "pair": "TESOURO/USD",
        "payment_symbol": "USDC",
        "notes": "USD price from bond_cost_in_usd on TESOURO-USDC feed",
    },
    "ktb": {
        "subject": "ch.mw.etherfuse.status.KTB-USD",
        "pair": "KTB/USD",
        "payment_symbol": "USDC",
        "notes": "Direct KTB-USD etherfuse feed",
    },
    "gilts": {
        "subject": "ch.mw.etherfuse.status.GILTS-GBP",
        "pair": "GILTS/USD",
        "payment_symbol": "USDC",
        "notes": "GBP feed; USD via bond_cost_in_usd (or fiat/fx fallback)",
    },
}


def fetch_raw_events(client: ClickHouseClient, subject: str) -> list[dict]:
    sql = f"""
    SELECT
      ts_event,
      subject,
      base64Encode(payload) AS payload_b64
    FROM market_events
    WHERE subject = '{subject}'
      AND payload != ''
      AND ts_event > toDateTime64('1970-01-02 00:00:00', 9)
    ORDER BY ts_event ASC
    """
    rows = client.query_rows(sql)

    for row in rows:
        row["payload"] = base64.b64decode(row.pop("payload_b64"))
    return rows


def aggregate_daily(rows: list[dict], feed: dict[str, str]) -> list[dict]:
    """Keep the last oracle update per calendar day."""
    by_day: dict[str, dict] = {}
    updates_per_day: dict[str, int] = defaultdict(int)

    for row in rows:
        ts_event = row["ts_event"]
        day_key = ts_event[:10]
        updates_per_day[day_key] += 1

        record = daily_record_from_row(
            ts_event=ts_event,
            subject=row["subject"],
            payload=row["payload"],
            pair=feed["pair"],
            payment_symbol=feed["payment_symbol"],
        )
        if record is None:
            continue

        by_day[day_key] = record

    daily = sorted(by_day.values(), key=lambda r: r["timestamp"])
    for item in daily:
        day = item["date"][:10]
        item["day"] = day
        item["updates_in_day"] = updates_per_day.get(day, 0)

    return daily


def save_asset_json(asset: str, feed: dict[str, str], daily: list[dict]) -> Path:
    output_dir = PROJECT_ROOT / "json" / f"oracle-{asset}"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{asset}_daily_prices.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(daily, f, ensure_ascii=False, indent=4)

    meta_path = output_dir / f"{asset}_meta.json"
    meta = {
        "asset": asset,
        "pair": feed["pair"],
        "subject": feed["subject"],
        "source": "clickhouse_oracle",
        "notes": feed.get("notes", ""),
        "record_count": len(daily),
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=4)

    return output_path


def run_assets(client: ClickHouseClient, assets: list[str]) -> dict[str, Path]:
    saved: dict[str, Path] = {}
    for asset in assets:
        if asset not in ORACLE_FEEDS:
            raise ValueError(f"Unknown asset '{asset}'. Options: {list(ORACLE_FEEDS)}")

        feed = ORACLE_FEEDS[asset]
        print(f"==> Fetching {asset} ({feed['subject']}) ...")
        rows = fetch_raw_events(client, feed["subject"])
        print(f"    raw events: {len(rows)}")

        daily = aggregate_daily(rows, feed)
        print(f"    daily records: {len(daily)}")
        if daily:
            print(f"    range: {daily[0]['day']} -> {daily[-1]['day']}")
            print(f"    last price_usd: {daily[-1]['price_usd']}")

        path = save_asset_json(asset, feed, daily)
        saved[asset] = path
        print(f"    saved: {path}")

    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch oracle bond daily prices from ClickHouse")
    parser.add_argument(
        "assets",
        nargs="*",
        choices=list(ORACLE_FEEDS.keys()),
        help="Assets to fetch (default: all)",
    )
    args = parser.parse_args()
    assets = args.assets or list(ORACLE_FEEDS.keys())

    client = ClickHouseClient()
    if not client.ping():
        raise SystemExit(
            "ClickHouse not reachable at localhost:8123. "
            "Run ./scripts/clickhouse_access.sh first."
        )

    run_assets(client, assets)


if __name__ == "__main__":
    main()
