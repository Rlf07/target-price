import re
from typing import Any

# Etherfuse bond_cost payloads are protobuf, but field names/values are readable in the blob.
_FIELD_NAMES = (
    "bond_cost_in_usd",
    "bond_cost_in_payment_token",
    "bond_cost_in_fiat",
    "fiat_exchange_rate_with_usd",
    "bond_symbol",
    "currency",
    "symbol",
    "mint",
)


def _payload_text(payload: str | bytes) -> str:
    if isinstance(payload, bytes):
        return payload.decode("latin-1", errors="ignore")
    return payload


def parse_etherfuse_bond_payload(payload: str | bytes) -> dict[str, str]:
    """Extract bond cost fields from an etherfuse status payload."""
    text = _payload_text(payload)
    out: dict[str, str] = {}
    for field in _FIELD_NAMES:
        match = re.search(rf"{field}\x12.([0-9.]+)", text)
        if match:
            out[field] = match.group(1).strip()
    return out


def price_usd_from_fields(fields: dict[str, str]) -> float | None:
    """Primary USD price from feed; fallback via fiat / FX rate."""
    raw = fields.get("bond_cost_in_usd")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass

    fiat = fields.get("bond_cost_in_fiat")
    fx = fields.get("fiat_exchange_rate_with_usd")
    if fiat and fx:
        try:
            return float(fiat) / float(fx)
        except (ValueError, ZeroDivisionError):
            return None
    return None


def daily_record_from_row(
    ts_event: str,
    subject: str,
    payload: str | bytes,
    pair: str,
    payment_symbol: str,
) -> dict[str, Any] | None:
    fields = parse_etherfuse_bond_payload(payload)
    price_usd = price_usd_from_fields(fields)
    if price_usd is None:
        return None

    from datetime import datetime

    # ClickHouse returns ISO-like timestamps, e.g. 2026-05-08 13:57:46.604391418
    dt = datetime.fromisoformat(ts_event.replace("Z", "+00:00").split(".")[0])

    return {
        "date": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "timestamp": int(dt.timestamp()),
        "price_usd": price_usd,
        "bond_cost_in_usd": float(fields.get("bond_cost_in_usd") or price_usd),
        "bond_cost_in_payment_token": _to_float(fields.get("bond_cost_in_payment_token")),
        "bond_cost_in_fiat": _to_float(fields.get("bond_cost_in_fiat")),
        "fiat_exchange_rate_with_usd": _to_float(fields.get("fiat_exchange_rate_with_usd")),
        "bond_symbol": fields.get("bond_symbol"),
        "currency": fields.get("currency"),
        "payment_symbol": fields.get("symbol") or payment_symbol,
        "pair": pair,
        "subject": subject,
        "source": "clickhouse_oracle",
    }


def _to_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None
