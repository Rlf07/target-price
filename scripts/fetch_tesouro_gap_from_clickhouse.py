"""Fill TESOURO/BRZ prices from last ClickHouse daily row until now via eth_getLogs.

Persists after every price (NDJSON) and every chunk (JSON checkpoint) so an
interrupted run can resume without re-fetching immutable chain data.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "0xc1DF935339989f398C59aF034fdfc13b2a84C4F2"
# Same AnswerUpdated topic0 observed on KTB / this Polygon feed
TOPIC0 = "0x0559884fd3a460db3073b7fc896cc77986f16e378210ded43186175bf646fc5f"
DECIMALS = 8
PAIR_NATIVE = "TESOURO/BRZ"
DAILY_PATH = ROOT / "json" / "oracle-tesouro" / "tesouro_daily_prices.json"
CH_ONLY_PATH = ROOT / "json" / "oracle-tesouro" / "tesouro_daily_prices_clickhouse_only.json"
OUT_PATH = ROOT / "json" / "oracle-tesouro" / "tesouro_prices_gap_from_clickhouse.json"
CACHE_NDJSON = ROOT / "json" / "oracle-tesouro" / "tesouro_prices_gap_cache.ndjson"
CHUNK = 50_000  # Polygon RPC often happier with mid-size ranges


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
    import requests

    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    last: Exception | None = None
    for attempt in range(retries):
        try:
            resp = requests.post(rpc, json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise RuntimeError(data["error"])
            return data["result"]
        except Exception as exc:  # noqa: BLE001
            last = exc
            print(f"  retry {attempt + 1} {method}: {type(exc).__name__}: {exc}")
            time.sleep(1.2 * (attempt + 1))
    assert last is not None
    raise last


def last_clickhouse_point() -> tuple[int, str]:
    path = CH_ONLY_PATH if CH_ONLY_PATH.is_file() else DAILY_PATH
    rows = json.loads(path.read_text(encoding="utf-8"))
    ch_rows = [r for r in rows if r.get("source") == "clickhouse_oracle"] or rows
    last = ch_rows[-1]
    return int(last["timestamp"]), str(last["date"])


def block_timestamp(rpc: str, block_number: int) -> int:
    block = rpc_call(rpc, "eth_getBlockByNumber", [hex(block_number), False])
    return int(block["timestamp"], 16)


def find_block_at_or_after(rpc: str, target_ts: int, latest: int) -> int:
    # Polygon mid-2025 was already ~60M+; May 2026 is well above that.
    lo, hi = 60_000_000, latest
    while lo < hi:
        mid = (lo + hi) // 2
        ts = block_timestamp(rpc, mid)
        if ts < target_ts:
            lo = mid + 1
        else:
            hi = mid
        time.sleep(0.05)
    return lo


def decode_log(log: dict) -> dict:
    topics = log["topics"]
    current = int(topics[1], 16)
    if current >= 2**255:
        current -= 2**256
    round_id = int(topics[2], 16) if len(topics) > 2 else None
    data = (log.get("data") or "0x")[2:]
    updated_at = int(data[:64], 16) if len(data) >= 64 else None
    return {
        "timestamp": updated_at,
        "date": (
            datetime.fromtimestamp(updated_at, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            if updated_at
            else None
        ),
        "price_native": current / (10**DECIMALS),
        "price_raw": current,
        "pair_native": PAIR_NATIVE,
        "round_id": round_id,
        "tx_hash": log.get("transactionHash"),
        "block_number": int(log["blockNumber"], 16),
        "log_index": int(log["logIndex"], 16),
    }


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            json.dump(payload, tmp, indent=2)
            tmp.write("\n")
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def price_key(p: dict) -> tuple:
    return (p.get("tx_hash"), p.get("log_index"), p.get("timestamp"), p.get("price_raw"))


def load_checkpoint(last_ts: int, last_date: str) -> dict:
    if OUT_PATH.is_file():
        state = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        if state.get("prices") is not None and state.get("next_block") is not None:
            prices = state.get("prices") or []
            state["prices"] = prices
            state["count"] = len(prices)
            state["clickhouse_last_timestamp"] = int(
                state.get("clickhouse_last_timestamp") or last_ts
            )
            state.setdefault("clickhouse_last_date", last_date)
            print(
                f"resume checkpoint: {len(prices)} prices, next_block={state['next_block']}, "
                f"complete={state.get('complete')}"
            )
            return state

    return {
        "contract": CONTRACT,
        "chain": "polygon",
        "decimals": DECIMALS,
        "pair_native": PAIR_NATIVE,
        "source": "eth_getLogs AnswerUpdated after last clickhouse daily",
        "clickhouse_last_date": last_date,
        "clickhouse_last_timestamp": last_ts,
        "from_block": None,
        "to_block": None,
        "next_block": None,
        "complete": False,
        "elapsed_seconds": 0,
        "count": 0,
        "prices": [],
    }


def append_prices_to_cache(new_prices: list[dict]) -> None:
    if not new_prices:
        return
    CACHE_NDJSON.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_NDJSON.open("a", encoding="utf-8") as fh:
        for p in new_prices:
            fh.write(json.dumps(p, separators=(",", ":")) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


def save_checkpoint(state: dict) -> None:
    state["count"] = len(state["prices"])
    atomic_write_json(OUT_PATH, state)


def main() -> None:
    rpc = load_env()["POLYGON_RPC_URL"]
    t0 = time.time()

    last_ts, last_date = last_clickhouse_point()
    print(f"ClickHouse last: {last_date} (ts={last_ts})")

    state = load_checkpoint(last_ts, last_date)
    last_ts = int(state["clickhouse_last_timestamp"])
    seen = {price_key(p) for p in state["prices"]}

    latest = int(rpc_call(rpc, "eth_blockNumber", []), 16)
    print(f"latest block={latest}")

    if state.get("from_block") is None:
        print("binary-search block for last ClickHouse timestamp...")
        state["from_block"] = find_block_at_or_after(rpc, last_ts, latest)
        state["next_block"] = state["from_block"]
        save_checkpoint(state)
        print(f"from_block={state['from_block']}")

    start = int(state["next_block"] or state["from_block"])
    state["complete"] = False
    state["to_block"] = latest

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
            if chunk > 2_000:
                chunk = max(2_000, chunk // 2)
                print(f"  shrink chunk -> {chunk}: {exc}")
                continue
            raise

        new_prices: list[dict] = []
        for log in logs:
            p = decode_log(log)
            if (p["timestamp"] or 0) <= last_ts:
                continue
            key = price_key(p)
            if key in seen:
                continue
            seen.add(key)
            new_prices.append(p)
            state["prices"].append(p)
            append_prices_to_cache([p])

        state["next_block"] = end + 1
        state["to_block"] = latest
        state["elapsed_seconds"] = round(time.time() - t0, 2)
        save_checkpoint(state)

        chunks += 1
        print(
            f"  [{chunks}] blocks {start}-{end}: +{len(new_prices)} "
            f"(total {len(state['prices'])}) saved [{state['elapsed_seconds']}s]"
        )
        start = end + 1
        time.sleep(0.15)

    state["complete"] = True
    state["next_block"] = latest + 1
    state["elapsed_seconds"] = round(time.time() - t0, 2)
    save_checkpoint(state)

    print(
        f"\nDONE complete={state['complete']} count={state['count']} "
        f"in {state['elapsed_seconds']}s -> {OUT_PATH}"
    )
    if state["prices"]:
        print(
            f"first: {state['prices'][0]['date']} "
            f"{state['prices'][0]['price_native']} {PAIR_NATIVE}"
        )
        print(
            f"last:  {state['prices'][-1]['date']} "
            f"{state['prices'][-1]['price_native']} {PAIR_NATIVE}"
        )


if __name__ == "__main__":
    main()
