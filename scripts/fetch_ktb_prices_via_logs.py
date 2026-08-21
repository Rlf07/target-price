"""Fetch all KTB oracle prices via eth_getLogs (AnswerUpdated) — no per-tx RPC."""

from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "0x0087a2b1b36DBB75963b8eD25DFB370Ec1604460"
# topic0 observado nos receipts KTB (diferente do Chainlink clássico no config)
TOPIC0 = "0x0559884fd3a460db3073b7fc896cc77986f16e378210ded43186175bf646fc5f"
DECIMALS = 8
OUT_FULL = ROOT / "json" / "oracle-ktb" / "ktb_prices_from_logs.json"
OUT_BENCH = ROOT / "json" / "oracle-ktb" / "ktb_getlogs_benchmark.json"


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def rpc_call(rpc: str, method: str, params: list, timeout: int = 120, retries: int = 5):
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
            print(f"  retry {attempt + 1} {method}: {type(exc).__name__}: {exc}")
            time.sleep(1.2 * (attempt + 1))
    assert last is not None
    raise last


def main() -> None:
    rpc = load_env()["MONAD_RPC_URL"]
    t0 = time.time()

    latest = int(rpc_call(rpc, "eth_blockNumber", []), 16)
    print(f"latest block={latest}")

    transfers = rpc_call(
        rpc,
        "alchemy_getAssetTransfers",
        [
            {
                "fromBlock": "0x0",
                "toBlock": "latest",
                "toAddress": CONTRACT,
                "category": ["external"],
                "maxCount": "0x1",
                "order": "asc",
            }
        ],
    )
    first = (transfers.get("transfers") or [None])[0]
    from_block = int(first["blockNum"], 16) if first else max(0, latest - 5_000_000)
    print(f"from_block={from_block}")

    chunk = 50_000
    start = from_block
    all_logs: list[dict] = []
    chunks_ok = 0
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
            all_logs.extend(logs)
            chunks_ok += 1
            if chunks_ok % 5 == 0 or end == latest:
                print(
                    f"  blocks {start}-{end}: +{len(logs)} "
                    f"(total {len(all_logs)}) [{time.time() - t0:.1f}s]"
                )
            start = end + 1
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if chunk > 2_000 and any(
                k in msg for k in ("range", "limit", "block", "response size", "10000")
            ):
                chunk = max(2_000, chunk // 2)
                print(f"  shrink chunk -> {chunk}: {exc}")
                continue
            raise

    prices = []
    for log in all_logs:
        topics = log.get("topics") or []
        if len(topics) < 2:
            continue
        current = int(topics[1], 16)
        if current >= 2**255:
            current -= 2**256
        round_id = int(topics[2], 16) if len(topics) > 2 else None
        data = (log.get("data") or "0x")[2:]
        updated_at = int(data[:64], 16) if len(data) >= 64 else None
        prices.append(
            {
                "timestamp": updated_at,
                "date": (
                    datetime.fromtimestamp(updated_at, tz=timezone.utc).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if updated_at
                    else None
                ),
                "price": current / (10**DECIMALS),
                "price_raw": current,
                "round_id": round_id,
                "tx_hash": log.get("transactionHash"),
                "block_number": int(log["blockNumber"], 16) if log.get("blockNumber") else None,
                "log_index": int(log["logIndex"], 16) if log.get("logIndex") else None,
            }
        )

    elapsed = time.time() - t0
    OUT_BENCH.parent.mkdir(parents=True, exist_ok=True)
    OUT_BENCH.write_text(
        json.dumps(
            {
                "contract": CONTRACT,
                "topic0": TOPIC0,
                "from_block": from_block,
                "to_block": latest,
                "chunk_size_final": chunk,
                "chunks": chunks_ok,
                "elapsed_seconds": round(elapsed, 2),
                "count": len(prices),
                "first": prices[0] if prices else None,
                "last": prices[-1] if prices else None,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    OUT_FULL.write_text(
        json.dumps(
            {
                "contract": CONTRACT,
                "chain": "monad",
                "decimals": DECIMALS,
                "pair": "KTB/USD",
                "source": "eth_getLogs AnswerUpdated topics[1]=current",
                "elapsed_seconds": round(elapsed, 2),
                "count": len(prices),
                "prices": prices,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\nDONE in {elapsed:.1f}s — {len(prices)} prices")
    if prices:
        print(f"first: {prices[0]['date']} {prices[0]['price']}")
        print(f"last:  {prices[-1]['date']} {prices[-1]['price']}")
    print(f"saved {OUT_FULL} ({OUT_FULL.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
