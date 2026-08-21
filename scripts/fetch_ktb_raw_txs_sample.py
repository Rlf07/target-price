"""Fetch first N raw txs to the KTB oracle contract via Monad RPC and save JSON."""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "0x0087a2b1b36DBB75963b8eD25DFB370Ec1604460"
OUT_PATH = ROOT / "json" / "oracle-ktb" / "ktb_raw_txs_sample.json"
LIMIT = 10


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def rpc_call(rpc: str, method: str, params: list, timeout: int = 90, retries: int = 6):
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    body = json.dumps(payload).encode()
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                rpc, data=body, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode())
            if "error" in data:
                raise RuntimeError(f"{method}: {data['error']}")
            return data["result"]
        except Exception as exc:  # noqa: BLE001 — sample script, retry any RPC blip
            last = exc
            wait = 1.5 * (attempt + 1)
            print(f"  retry {attempt + 1}/{retries} {method}: {type(exc).__name__}: {exc}")
            time.sleep(wait)
    assert last is not None
    raise last


def main() -> None:
    env = load_env()
    rpc = env["MONAD_RPC_URL"]

    transfers = rpc_call(
        rpc,
        "alchemy_getAssetTransfers",
        [
            {
                "fromBlock": "0x0",
                "toBlock": "latest",
                "toAddress": CONTRACT,
                "category": ["external"],
                "withMetadata": True,
                "excludeZeroValue": False,
                "maxCount": hex(LIMIT),
                "order": "asc",
            }
        ],
    )
    transfer_list = transfers.get("transfers") or []
    hashes: list[str] = []
    seen: set[str] = set()
    for t in transfer_list:
        h = t.get("hash")
        if h and h not in seen:
            seen.add(h)
            hashes.append(h)
    hashes = hashes[:LIMIT]
    print(f"hashes ({len(hashes)}):")
    for h in hashes:
        print(" ", h)

    raw_txs = []
    for i, h in enumerate(hashes, 1):
        print(f"[{i}/{len(hashes)}] {h}")
        time.sleep(0.4)
        tx = rpc_call(rpc, "eth_getTransactionByHash", [h])
        time.sleep(0.3)
        receipt = rpc_call(rpc, "eth_getTransactionReceipt", [h])
        block_info = None
        if tx and tx.get("blockNumber") is not None:
            time.sleep(0.3)
            block = rpc_call(rpc, "eth_getBlockByNumber", [tx["blockNumber"], False])
            block_info = {
                "number": block.get("number"),
                "timestamp": block.get("timestamp"),
                "hash": block.get("hash"),
            }
        raw_txs.append(
            {
                "tx": tx,
                "receipt": receipt,
                "block": block_info,
                "transfer_meta": next(
                    (t for t in transfer_list if t.get("hash") == h),
                    None,
                ),
            }
        )

    out = {
        "contract": CONTRACT,
        "chain": "monad",
        "rpc_source": "MONAD_RPC_URL",
        "count": len(raw_txs),
        "note": "Primeiras 10 txs (asc) em raw via RPC Alchemy — sem decode.",
        "transactions": raw_txs,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nsaved {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")
    for i, item in enumerate(raw_txs, 1):
        tx = item["tx"] or {}
        inp = tx.get("input") or "0x"
        print(
            f"{i} selector={inp[:10]} input_bytes={len(inp[2]) // 2} "
            f"block={tx.get('blockNumber')} hash={tx.get('hash')}"
        )


if __name__ == "__main__":
    main()
