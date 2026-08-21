"""
Fetch bond oracle prices from on-chain contract transactions.

Sources (per asset):
  - ClickHouse `transactions` (Polygon tesouro has ~966 txs; gilts/ktb usually empty)
  - RPC logs via POLYGON_RPC_URL / MONAD_RPC_URL (for live / gilts / monad ktb)

Triangulation:
  - tesouro/BRZ -> USD via forex BRL (BRZ ≈ BRL)
  - gilts/GBP -> USD via forex GBP
  - ktb/USD -> direct

Usage:
  python daily_onchain_oracle_prices.py
  python daily_onchain_oracle_prices.py tesouro
  python daily_onchain_oracle_prices.py --merge   # merge with etherfuse JSON
"""

import argparse
import json
from pathlib import Path

from src.clickhouse_client import ClickHouseClient
from src.onchain_oracle_config import ONCHAIN_ORACLE_CONTRACTS
from src.onchain_price_fetch import fetch_onchain_daily_for_asset

PROJECT_ROOT = Path(__file__).resolve().parent


def merge_daily_records(
    etherfuse: list[dict],
    onchain: list[dict],
) -> list[dict]:
    """Per day: prefer on-chain if same day exists in both; else keep etherfuse."""
    by_day: dict[str, dict] = {}

    for row in etherfuse:
        day = row.get("day") or row["date"][:10]
        by_day[day] = row

    for row in onchain:
        day = row["day"]
        prev = by_day.get(day)
        if prev is None:
            by_day[day] = row
            continue
        # Prefer on-chain when both exist (situational fresher feed)
        prev_src = prev.get("source", "")
        if prev_src.startswith("clickhouse_oracle") and row.get("source", "").startswith(
            ("clickhouse_tx", "rpc_")
        ):
            by_day[day] = row
        elif row["timestamp"] >= prev.get("timestamp", 0):
            by_day[day] = row

    merged = sorted(by_day.values(), key=lambda r: r["timestamp"])
    for item in merged:
        if "day" not in item:
            item["day"] = item["date"][:10]
    return merged


def save_asset(asset: str, daily: list[dict], suffix: str = "") -> Path:
    output_dir = PROJECT_ROOT / "json" / f"oracle-{asset}"
    output_dir.mkdir(parents=True, exist_ok=True)
    name = f"{asset}_daily_prices{suffix}.json"
    path = output_dir / name
    with open(path, "w", encoding="utf-8") as f:
        json.dump(daily, f, ensure_ascii=False, indent=4)
    return path


def load_etherfuse_json(asset: str) -> list[dict]:
    path = PROJECT_ROOT / "json" / f"oracle-{asset}" / f"{asset}_daily_prices.json"
    if not path.is_file():
        return []
    return json.load(path.open(encoding="utf-8"))


def run(asset: str, client: ClickHouseClient | None, merge: bool) -> None:
    print(f"==> {asset} on-chain ({ONCHAIN_ORACLE_CONTRACTS[asset]['address']})")
    onchain = fetch_onchain_daily_for_asset(asset, client=client)
    print(f"    on-chain daily: {len(onchain)}")
    if onchain:
        print(f"    range: {onchain[0]['day']} -> {onchain[-1]['day']}")
        print(f"    last price_usd: {onchain[-1]['price_usd']}")

    onchain_path = save_asset(asset, onchain, suffix="_onchain")
    print(f"    saved: {onchain_path}")

    if merge:
        etherfuse = load_etherfuse_json(asset)
        merged = merge_daily_records(etherfuse, onchain)
        main_path = save_asset(asset, merged)
        print(f"    merged ({len(etherfuse)} etherfuse + {len(onchain)} on-chain) -> {len(merged)} days")
        print(f"    saved: {main_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch on-chain oracle daily prices")
    parser.add_argument("assets", nargs="*", choices=list(ONCHAIN_ORACLE_CONTRACTS.keys()))
    parser.add_argument("--merge", action="store_true", help="Merge into main daily JSON")
    args = parser.parse_args()
    assets = args.assets or list(ONCHAIN_ORACLE_CONTRACTS.keys())

    client = None
    try:
        ch = ClickHouseClient()
        if ch.ping():
            client = ch
            print("ClickHouse: ok")
        else:
            print("ClickHouse: não disponível (só RPC)")
    except Exception:
        print("ClickHouse: não disponível (só RPC)")

    for asset in assets:
        try:
            run(asset, client, merge=args.merge)
        except Exception as exc:
            print(f"    ERRO {asset}: {exc}")
        print()


if __name__ == "__main__":
    main()
