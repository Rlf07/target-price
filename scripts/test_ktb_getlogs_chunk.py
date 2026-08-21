"""Micro-test: one eth_getLogs chunk around first known KTB price block."""

import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
env = {}
for line in (ROOT / ".env").read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    env[k.strip()] = v.strip()

rpc = env["MONAD_RPC_URL"]
contract = "0x0087a2b1b36DBB75963b8eD25DFB370Ec1604460"
topic0 = "0x0559884fd3a460db3073b7fc896cc77986f16e378210ded43186175bf646fc5f"
start = 0x35DA432  # first price block from sample
end = start + 20_000

payload = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "eth_getLogs",
    "params": [
        {
            "address": contract,
            "fromBlock": hex(start),
            "toBlock": hex(end),
            "topics": [topic0],
        }
    ],
}
t0 = time.time()
req = urllib.request.Request(
    rpc, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req, timeout=60) as resp:
    data = json.loads(resp.read().decode())
elapsed = time.time() - t0
if "error" in data:
    raise SystemExit(data["error"])
logs = data["result"]
prices = [int(log["topics"][1], 16) / 1e8 for log in logs]
print(f"chunk {start}-{end}: {len(logs)} prices in {elapsed:.2f}s")
if prices:
    print(f"first={prices[0]} last={prices[-1]}")
