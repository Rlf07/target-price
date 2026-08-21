"""Decode oracle price updates from transaction calldata or Chainlink logs."""

from __future__ import annotations

from typing import Any

from web3 import Web3


def normalize_hex(data: str | bytes) -> str:
    if isinstance(data, bytes):
        return data.hex()
    value = data.strip().lower()
    if value.startswith("0x"):
        value = value[2:]
    return value


def decode_transmit_price(
    data: str | bytes,
    selector: str = "2831fff3",
    decimals: int = 8,
) -> float | None:
    """
    Decode price from transmit-style calldata.
    Pattern observed on Polygon oracle txs: selector + first uint256 = answer.
    """
    raw = normalize_hex(data)
    if len(raw) < 8 + 64:
        return None
    if raw[:8] != selector.lower():
        return None
    answer = int(raw[8:8 + 64], 16)
    return answer / (10 ** decimals)


def decode_answer_updated_log(log: dict[str, Any], decimals: int = 8) -> float | None:
    topics = log.get("topics") or []
    if not topics:
        return None
    if topics[0].lower().replace("0x", "") != "0559884fd3a460db3073b7fc896cc77986f16e378084d791dcde54156afa0756":
        return None
    data = normalize_hex(log.get("data") or "")
    if len(data) < 64:
        return None
    answer = int(data[:64], 16)
    # int256 sign handling
    if answer >= 2 ** 255:
        answer -= 2 ** 256
    return answer / (10 ** decimals)


def read_latest_round_data(
    w3: Web3,
    address: str,
    decimals: int = 8,
) -> tuple[float, int] | None:
    """Fallback: read latestRoundData() from aggregator contract."""
    agg_abi = [
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
    ]
    contract = w3.eth.contract(address=Web3.to_checksum_address(address), abi=agg_abi)
    try:
        rd = contract.functions.latestRoundData().call()
        price = rd[1] / (10 ** decimals)
        updated_at = int(rd[3])
        return price, updated_at
    except Exception:
        return None
