"""
Fill missing days in oracle bond feeds using on-chain round history.

Approach:
- Load existing json/oracle-{asset}/{asset}_daily_prices.json
- Find last available day in that file
- Starting from latestRoundData(), walk backwards with getRoundData(roundId)
  and pick the first (latest) price per calendar day within the missing gap
- Triangulate to USD when needed (tesouro/BRZ -> USD via forex brl, gilts/GBP -> USD via forex gbp)
- Merge into the main JSON (fill gaps only; keep existing records as-is)
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from web3 import Web3

from src.onchain_oracle_config import ONCHAIN_ORACLE_CONTRACTS

# Load env vars (RPC URLs etc.)
from dotenv import load_dotenv
load_dotenv(Path(".env"))


def _utc_from_ts(ts: int) -> datetime:
    return datetime.fromtimestamp(int(ts), tz=timezone.utc)


def _day_str_from_ts(ts: int) -> str:
    return _utc_from_ts(ts).strftime("%Y-%m-%d")


def _load_existing(asset: str) -> list[dict[str, Any]]:
    path = Path("json") / f"oracle-{asset}" / f"{asset}_daily_prices.json"
    if not path.is_file():
        raise FileNotFoundError(f"Missing oracle JSON: {path}")
    return json.load(path.open(encoding="utf-8"))


def _save_asset(asset: str, records: list[dict[str, Any]]) -> None:
    path = Path("json") / f"oracle-{asset}" / f"{asset}_daily_prices.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=4)

    # meta (light touch)
    meta_path = Path("json") / f"oracle-{asset}" / f"{asset}_meta.json"
    meta = {
        "asset": asset,
        "source": "oracle_round_history_fill",
        "record_count": len(records),
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=4)


def _load_forex_rates(forex_asset: str) -> dict[str, float]:
    # Matches app/providers/history_provider.json_path_for_asset() behavior
    if forex_asset == "mxn":
        path = Path("json/forex-mxn/daily_prices.json")
    else:
        path = Path(f"json/forex-{forex_asset}/{forex_asset}_daily_prices.json")
    if not path.is_file():
        raise FileNotFoundError(f"Missing forex JSON: {path}")

    data = json.load(path.open(encoding="utf-8"))
    out: dict[str, float] = {}
    for row in data:
        day = str(row.get("date", ""))[:10]
        vwap = row.get("price_vwap")
        if day and vwap is not None:
            out[day] = float(vwap)
    return out


def _forex_rate_for_day(rates: dict[str, float], day: str) -> float:
    if day in rates:
        return rates[day]
    # use previous available day (piecewise constant)
    prior = [d for d in rates.keys() if d <= day]
    if not prior:
        raise ValueError(f"No forex rate found for {day}")
    return rates[max(prior)]


def _triangulate_to_usd(price_native: float, day: str, triangulate_via_forex: str | None) -> float:
    if triangulate_via_forex is None:
        return price_native
    rates = _load_forex_rates(triangulate_via_forex)
    fx = _forex_rate_for_day(rates, day)
    return price_native * fx


def _build_round_history_walker(w3: Web3, address: str):
    abi = [
        {
            "inputs": [],
            "name": "latestRoundData",
            "outputs": [
                {"type": "uint80"},
                {"type": "int256"},
                {"type": "uint256"},
                {"type": "uint256"},
                {"type": "uint80"},
            ],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [{"type": "uint80", "name": "roundId"}],
            "name": "getRoundData",
            "outputs": [
                {"type": "uint80"},
                {"type": "int256"},
                {"type": "uint256"},
                {"type": "uint256"},
                {"type": "uint80"},
            ],
            "stateMutability": "view",
            "type": "function",
        },
        {
            "inputs": [],
            "name": "decimals",
            "outputs": [{"type": "uint8"}],
            "stateMutability": "view",
            "type": "function",
        },
    ]
    return w3.eth.contract(address=Web3.to_checksum_address(address), abi=abi)


def _fetch_missing_days_from_rounds(
    asset: str,
    start_day: str,
    end_day: str,
    max_round_steps: int = 20000,
) -> list[dict[str, Any]]:
    cfg = ONCHAIN_ORACLE_CONTRACTS[asset]
    chain = cfg["chain"]
    address = cfg["address"]
    decimals = int(cfg["decimals"])
    triangulate_via_forex = cfg.get("triangulate_via_forex")

    rpc_env = "POLYGON_RPC_URL" if chain == "polygon" else "MONAD_RPC_URL"
    rpc_url = os.getenv(rpc_env, "").strip()
    if not rpc_url:
        raise RuntimeError(f"Missing RPC env: {rpc_env} for asset {asset}")

    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout":60}))
    if not w3.is_connected():
        raise RuntimeError(f"RPC not reachable ({rpc_env}) for asset {asset}")

    c = _build_round_history_walker(w3, address)

    # start from latest
    latest = c.functions.latestRoundData().call()
    latest_round_id = int(latest[0])

    start_dt = datetime.fromisoformat(start_day).replace(tzinfo=timezone.utc)
    end_dt = datetime.fromisoformat(end_day).replace(tzinfo=timezone.utc)

    by_day: dict[str, dict[str, Any]] = {}

    # Walk backwards: latest -> older
    round_id = latest_round_id
    steps = 0
    while round_id > 0 and steps < max_round_steps:
        steps += 1
        rd = c.functions.getRoundData(round_id).call()
        updated_at = int(rd[3])
        if updated_at <= 0:
            round_id -= 1
            continue

        dt = _utc_from_ts(updated_at)
        if dt < start_dt:
            break
        if dt > end_dt:
            round_id -= 1
            continue

        day = dt.strftime("%Y-%m-%d")
        if day not in by_day:
            answer = int(rd[1])
            price_native = answer / (10**decimals)
            price_usd = _triangulate_to_usd(price_native, day, triangulate_via_forex)

            by_day[day] = {
                "date": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "timestamp": updated_at,
                "price_usd": float(price_usd),
                # kept for compatibility / future debugging
                "price_native": float(price_native),
                "pair_native": cfg.get("pair_native"),
                "pair": f"{cfg.get('pair_native').split('/')[0]}/USD",
                "contract": address,
                "chain": chain,
                "source": "oracle_round_history_fill",
                "day": day,
                "updates_in_day": 1,
            }

        round_id -= 1

    filled = [by_day[d] for d in sorted(by_day.keys())]
    return filled


def fill_assets(assets: list[str], force: bool = False, max_round_steps: int = 20000) -> None:
    # end_day = hoje (UTC)
    today_utc = datetime.now(tz=timezone.utc)
    end_day = today_utc.strftime("%Y-%m-%d")

    for asset in assets:
        if asset not in ONCHAIN_ORACLE_CONTRACTS:
            raise ValueError(f"asset inválido: {asset}")

        existing = _load_existing(asset)
        existing_days = {str(r.get("day") or str(r.get("date", ""))[:10]) for r in existing}
        last_day = max(existing_days)
        if force:
            last_day_dt = datetime.fromisoformat(last_day).replace(tzinfo=timezone.utc)
            start_day_dt = last_day_dt
        else:
            start_day_dt = datetime.fromisoformat(last_day).replace(tzinfo=timezone.utc)

        # fill only missing days after the last day present in JSON
        start_next_day = (start_day_dt + timedelta(days=1)).strftime("%Y-%m-%d")

        # If already up to date, skip
        if not force and last_day >= end_day:
            print(f"{asset}: already up-to-date ({last_day})", flush=True)
            continue

        missing_start = start_next_day
        print(
            f"{asset}: filling from {missing_start} to {end_day} (last in json: {last_day})",
            flush=True,
        )

        filled = _fetch_missing_days_from_rounds(
            asset=asset,
            start_day=missing_start,
            end_day=end_day,
            max_round_steps=max_round_steps,
        )
        print(
            f"{asset}: fetched {len(filled)} daily points from on-chain rounds",
            flush=True,
        )
        if not filled:
            continue

        # merge: keep existing, append missing days
        merged_days = set(existing_days)
        merged = existing[:]
        for row in filled:
            day = row["day"]
            if day in merged_days:
                continue
            merged.append(row)
            merged_days.add(day)

        # sort by timestamp/date
        merged_sorted = sorted(merged, key=lambda r: r.get("timestamp") or 0)
        _save_asset(asset, merged_sorted)
        print(f"{asset}: saved merged json -> {len(merged_sorted)} records", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fill missing oracle days using getRoundData history"
    )
    parser.add_argument(
        "assets",
        nargs="*",
        default=list(ONCHAIN_ORACLE_CONTRACTS.keys()),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild from last day even if up-to-date",
    )
    parser.add_argument(
        "--max-round-steps",
        type=int,
        default=5000,
        help="Safety cap for roundId walkback (avoid long runs)",
    )
    args = parser.parse_args()

    fill_assets(args.assets, force=args.force, max_round_steps=args.max_round_steps)


if __name__ == "__main__":
    main()
