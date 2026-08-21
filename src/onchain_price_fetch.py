"""Fetch on-chain oracle prices from ClickHouse transactions and optional RPC."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from web3 import Web3

from src.clickhouse_client import ClickHouseClient
from src.onchain_oracle_config import ANSWER_UPDATED_TOPIC, ONCHAIN_ORACLE_CONTRACTS
from src.onchain_price_decoder import (
    decode_answer_updated_log,
    decode_transmit_price,
    read_latest_round_data,
)


def _load_forex_daily_rates(forex_asset: str) -> dict[str, float]:
    """Map YYYY-MM-DD -> USD per unit of forex asset (price_vwap)."""
    import json
    from pathlib import Path

    path = Path(f"json/forex-{forex_asset}/{forex_asset}_daily_prices.json")
    if forex_asset == "mxn":
        path = Path("json/forex-mxn/daily_prices.json")
    if not path.is_file():
        return {}

    data = json.load(path.open(encoding="utf-8"))
    out: dict[str, float] = {}
    for row in data:
        day = row.get("date", "")[:10]
        vwap = row.get("price_vwap")
        if day and vwap is not None:
            out[day] = float(vwap)
    return out


def _forex_rate_for_day(rates: dict[str, float], day: str) -> float | None:
    if day in rates:
        return rates[day]
    prior = [d for d in rates if d <= day]
    if not prior:
        return None
    return rates[max(prior)]


def triangulate_to_usd(
    price_native: float,
    day: str,
    forex_asset: str | None,
) -> tuple[float, str | None]:
    if forex_asset is None:
        return price_native, None
    rates = _load_forex_daily_rates(forex_asset)
    fx = _forex_rate_for_day(rates, day)
    if fx is None:
        raise ValueError(f"Sem FX {forex_asset}/USD para o dia {day}")
    # price_native in quote (e.g. BRZ per TESOURO); forex vwap = USD per unit
    return price_native * fx, fx


def fetch_tx_updates_from_clickhouse(
    client: ClickHouseClient,
    address: str,
    chain: str,
    selector: str,
    decimals: int,
) -> list[dict[str, Any]]:
    addr = address.lower()
    sql = f"""
    SELECT
      block_timestamp,
      data,
      hash AS tx_hash,
      chain_name
    FROM transactions
    WHERE lower(to_address) = '{addr}'
      AND chain_name = '{chain}'
      AND data != ''
    ORDER BY block_timestamp ASC
    """
    rows = client.query_rows(sql)
    updates: list[dict[str, Any]] = []
    for row in rows:
        price = decode_transmit_price(row["data"], selector=selector, decimals=decimals)
        if price is None:
            continue
        ts = int(row["block_timestamp"])
        updates.append(
            {
                "timestamp": ts,
                "date": datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
                "price_native": price,
                "tx_hash": row["tx_hash"],
                "chain": row["chain_name"],
                "source": "clickhouse_tx",
            }
        )
    return updates


def fetch_logs_from_rpc(
    rpc_url: str,
    address: str,
    selector: str,
    decimals: int,
    from_block: int = 0,
    to_block: str | int = "latest",
    chunk_size: int = 2000,
) -> list[dict[str, Any]]:
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 60}))
    if not w3.is_connected():
        raise RuntimeError(f"RPC não conectou: {rpc_url}")

    checksum = Web3.to_checksum_address(address)
    latest = w3.eth.block_number if to_block == "latest" else int(to_block)
    start = from_block
    updates: list[dict[str, Any]] = []

    while start <= latest:
        end = min(start + chunk_size - 1, latest)
        logs = w3.eth.get_logs(
            {
                "address": checksum,
                "fromBlock": start,
                "toBlock": end,
                "topics": [ANSWER_UPDATED_TOPIC],
            }
        )
        for log in logs:
            price = decode_answer_updated_log(dict(log), decimals=decimals)
            if price is None:
                continue
            block = w3.eth.get_block(log["blockNumber"])
            ts = int(block["timestamp"])
            updates.append(
                {
                    "timestamp": ts,
                    "date": datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
                    "price_native": price,
                    "tx_hash": log["transactionHash"].hex(),
                    "chain": str(w3.eth.chain_id),
                    "source": "rpc_log",
                }
            )
        start = end + 1

    # Also scan recent txs to contract for transmit selector (some feeds may not emit AnswerUpdated)
    # Lightweight: only last N blocks via filter - skip for MVP unless logs empty

    if not updates:
        snap = read_latest_round_data(w3, checksum, decimals=decimals)
        if snap:
            price, ts = snap
            updates.append(
                {
                    "timestamp": ts,
                    "date": datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S"),
                    "price_native": price,
                    "tx_hash": None,
                    "chain": str(w3.eth.chain_id),
                    "source": "rpc_latest_round",
                }
            )

    return sorted(updates, key=lambda r: r["timestamp"])


def aggregate_daily(updates: list[dict[str, Any]], config: dict) -> list[dict[str, Any]]:
    """Last update per calendar day with USD triangulation when needed."""
    by_day: dict[str, dict] = {}
    updates_per_day: dict[str, int] = {}

    forex_asset = config.get("triangulate_via_forex")

    for row in updates:
        day = row["date"][:10]
        updates_per_day[day] = updates_per_day.get(day, 0) + 1
        price_native = row["price_native"]
        price_usd, fx_rate = triangulate_to_usd(price_native, day, forex_asset)

        record = {
            "date": row["date"],
            "timestamp": row["timestamp"],
            "price_native": price_native,
            "price_usd": price_usd,
            "pair_native": config["pair_native"],
            "pair": (
                f"{config['pair_native'].split('/')[0]}/USD"
                if forex_asset
                else config["pair_native"]
            ),
            "quote_asset": config["quote_asset"],
            "fx_rate_usd": fx_rate,
            "fx_source": f"forex-{forex_asset}" if forex_asset else None,
            "contract": config["address"],
            "chain": config["chain"],
            "tx_hash": row.get("tx_hash"),
            "source": row["source"],
        }

        by_day[day] = record

    daily = sorted(by_day.values(), key=lambda r: r["timestamp"])
    for item in daily:
        day = item["date"][:10]
        item["day"] = day
        item["updates_in_day"] = updates_per_day.get(day, 0)
    return daily


def fetch_onchain_daily_for_asset(
    asset: str,
    client: ClickHouseClient | None = None,
) -> list[dict[str, Any]]:
    if asset not in ONCHAIN_ORACLE_CONTRACTS:
        raise ValueError(f"Ativo on-chain desconhecido: {asset}")

    config = ONCHAIN_ORACLE_CONTRACTS[asset]
    updates: list[dict[str, Any]] = []

    if client is not None:
        try:
            updates.extend(
                fetch_tx_updates_from_clickhouse(
                    client,
                    config["address"],
                    config["chain"],
                    config["transmit_selector"],
                    config["decimals"],
                )
            )
        except Exception:
            pass

    rpc_env = "POLYGON_RPC_URL" if config["chain"] == "polygon" else "MONAD_RPC_URL"
    rpc_url = os.getenv(rpc_env, "").strip()
    if rpc_url:
        try:
            rpc_updates = fetch_logs_from_rpc(
                rpc_url,
                config["address"],
                config["transmit_selector"],
                config["decimals"],
            )
            updates.extend(rpc_updates)
        except Exception as exc:
            if not updates:
                raise RuntimeError(f"Falha RPC ({rpc_env}): {exc}") from exc

    if not updates:
        raise RuntimeError(
            f"Sem updates on-chain para {asset}. "
            f"ClickHouse txs ou {rpc_env} necessários."
        )

    # Dedupe by timestamp keeping last per ts
    dedup = {u["timestamp"]: u for u in updates}
    return aggregate_daily(list(dedup.values()), config)
