"""Fetch KTB on-chain prices from last ClickHouse day until now (chunked getLogs)."""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "0x0087a2b1b36DBB75963b8eD25DFB370Ec1604460"
TOPIC0 = "0x0559884fd3a460db3073b7fc896cc77986f16e378210ded43186175bf646fc5f"
DECIMALS = 8
CHUNK = 50_000
CH_JSON = ROOT / "json" / "oracle-ktb" / "ktb_daily_prices.json"
OUT = ROOT / "json" / "oracle-ktb" / "ktb_prices_gap_fill.json"


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def rpc_call(rpc: str, method: str, params: list, timeout: int = 90, retries: int = 5):
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                rpc, data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
            if "error" in data:
                raise RuntimeError(data["error"])
            return data["result"]
        except Exception as exc:  # noqa: BLE001
            last = exc
            print(f"  retry {attempt + 1} {method}: {type(exc).__name__}")
            time.sleep(1.2 * (attempt + 1))
    assert last is not None
    raise last


def block_ts(rpc: str, n: int) -> int:
    block = rpc_call(rpc, "eth_getBlockByNumber", [hex(n), False])
    return int(block["timestamp"], 16)


def find_block_at_or_after(rpc: str, target_ts: int, latest: int) -> int:
    """Binary search: first block with timestamp >= target_ts."""
    lo, hi = 0, latest
    # Narrow lo with a coarse estimate (~1s/block on Monad is optimistic; use wide band)
    while lo < hi:
        mid = (lo + hi) // 2
        ts = block_ts(rpc, mid)
        if ts < target_ts:
            lo = mid + 1
        else:
            hi = mid
        time.sleep(0.05)
    return lo


def decode_log(log: dict) -> dict | None:
    topics = log.get("topics") or []
    if len(topics) < 2:
        return None
    current = int(topics[1], 16)
    if current >= 2**255:
        current -= 2**256
    data = (log.get("data") or "0x")[2:]
    updated_at = int(data[:64], 16) if len(data) >= 64 else None
    if updated_at is None:
        return None
    return {
        "timestamp": updated_at,
        "date": datetime.fromtimestamp(updated_at, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "price": current / (10**DECIMALS),
        "price_raw": current,
        "round_id": int(topics[2], 16) if len(topics) > 2 else None,
        "tx_hash": log.get("transactionHash"),
        "block_number": int(log["blockNumber"], 16) if log.get("blockNumber") else None,
    }


def main() -> None:
    rpc = load_env()["MONAD_RPC_URL"]
    ch = json.loads(CH_JSON.read_text(encoding="utf-8"))
    last = ch[-1]
    last_ts = int(last["timestamp"])
    print(f"ClickHouse last: {last['date']} ts={last_ts}")

    t0 = time.time()
    latest = int(rpc_call(rpc, "eth_blockNumber", []), 16)
    print(f"latest block={latest}")

    print("binary-searching from_block...")
    from_block = find_block_at_or_after(rpc, last_ts, latest)
    # back up one chunk to not miss boundary
    from_block = max(0, from_block - CHUNK)
    print(f"from_block={from_block} ({time.time() - t0:.1f}s)")

    prices: list[dict] = []
    start = from_block
    chunk = CHUNK
    chunks = 0
    while start <= latest:
        end = min(start + chunk - 1, latest)
        try:
            logs = rpc_call(
                rpc,
                "eth_getLogs",
                [
                    {
                        "address": CONTRACT,
                        "fromBlock": hex(start),
                        "toBlock": hex(end),
                        "topics": [TOPIC0],
                    }
                ],
            )
        except Exception as exc:  # noqa: BLE001
            if chunk > 5_000:
                chunk = max(5_000, chunk // 2)
                print(f"  shrink chunk -> {chunk}: {exc}")
                continue
            raise

        for log in logs:
            row = decode_log(log)
            if row and row["timestamp"] > last_ts:
                prices.append(row)

        chunks += 1
        print(
            f"  [{chunks}] blocks {start}-{end}: logs={len(logs)} "
            f"kept={len(prices)} [{time.time() - t0:.1f}s]"
        )
        start = end + 1
        time.sleep(0.15)

    prices.sort(key=lambda r: (r["timestamp"], r.get("block_number") or 0))
    out = {
        "contract": CONTRACT,
        "chain": "monad",
        "decimals": DECIMALS,
        "pair": "KTB/USD",
        "clickhouse_last": {
            "date": last["date"],
            "timestamp": last_ts,
            "day": last.get("day"),
        },
        "from_block": from_block,
        "to_block": latest,
        "elapsed_seconds": round(time.time() - t0, 2),
        "count": len(prices),
        "prices": prices,
    }
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nDONE {len(prices)} prices in {out['elapsed_seconds']}s -> {OUT}")
    if prices:
        print(f"first: {prices[0]['date']} {prices[0]['price']}")
        print(f"last:  {prices[-1]['date']} {prices[-1]['price']}")


if __name__ == "__main__":
    main()
