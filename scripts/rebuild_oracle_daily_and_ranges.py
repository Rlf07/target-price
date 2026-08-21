"""Rebuild oracle daily USD series from CH + onchain gaps, then run expected ranges."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from src.onchain_price_fetch import triangulate_to_usd

ROOT = Path(__file__).resolve().parents[1]


def _backup_ch_only(daily_path: Path, backup_path: Path) -> None:
    if backup_path.is_file():
        return
    if not daily_path.is_file():
        return
    rows = json.loads(daily_path.read_text(encoding="utf-8"))
    # only backup if still CH-only (or mixed without onchain yet)
    if all(r.get("source") != "onchain_oracle" for r in rows):
        shutil.copy(daily_path, backup_path)
        print(f"backup -> {backup_path}")


def _load_ch_rows(daily_path: Path, backup_path: Path) -> list[dict]:
    path = backup_path if backup_path.is_file() else daily_path
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [r for r in rows if r.get("source") == "clickhouse_oracle"] or rows


def _aggregate_onchain_daily(
    gap: dict,
    *,
    forex: str | None,
    payment_symbol: str,
    subject: str,
    pair_native: str,
) -> list[dict]:
    last_ts = int(gap["clickhouse_last_timestamp"])
    ticks: list[dict] = []
    missing = 0
    for p in gap.get("prices") or []:
        if (p.get("timestamp") or 0) <= last_ts:
            continue
        day = (p.get("date") or "")[:10]
        native = float(p.get("price_native", p.get("price")))
        try:
            price_usd, fx = triangulate_to_usd(native, day, forex)
        except ValueError:
            missing += 1
            continue
        row = dict(p)
        row["price_native"] = native
        row["price_usd"] = price_usd
        row["fx_rate_usd"] = fx
        row["fx_source"] = f"forex-{forex}" if forex else None
        ticks.append(row)
    if missing:
        print(f"  missing FX days skipped ticks={missing}")

    by_day: dict[str, dict] = {}
    updates: dict[str, int] = {}
    for t in ticks:
        day = t["date"][:10]
        updates[day] = updates.get(day, 0) + 1
        by_day[day] = t

    out = []
    for day in sorted(by_day):
        t = by_day[day]
        fx = t.get("fx_rate_usd")
        out.append(
            {
                "date": t["date"],
                "timestamp": t["timestamp"],
                "price_usd": t["price_usd"],
                "price_native": t["price_native"],
                "pair_native": pair_native,
                "pair": f"{pair_native.split('/')[0]}/USD",
                "fx_rate_usd": fx,
                "fx_source": t.get("fx_source"),
                "bond_cost_in_usd": t["price_usd"],
                "bond_cost_in_payment_token": t["price_native"],
                "bond_cost_in_fiat": t["price_native"],
                "fiat_exchange_rate_with_usd": (1.0 / fx) if fx else None,
                "bond_symbol": None,
                "currency": None,
                "payment_symbol": payment_symbol,
                "subject": subject,
                "source": "onchain_oracle",
                "contract": gap["contract"],
                "chain": gap.get("chain"),
                "tx_hash": t.get("tx_hash"),
                "day": day,
                "updates_in_day": updates[day],
            }
        )
    return out


def _merge(ch_rows: list[dict], onchain_daily: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for r in ch_rows:
        day = r.get("day") or r["date"][:10]
        row = dict(r)
        row["day"] = day
        merged[day] = row
    for r in onchain_daily:
        day = r["day"]
        prev = merged.get(day)
        if prev is None or int(r["timestamp"]) >= int(prev["timestamp"]):
            merged[day] = r
    return [merged[d] for d in sorted(merged)]


def rebuild_asset(
    asset: str,
    *,
    forex: str | None,
    payment_symbol: str,
    pair_native: str,
    subject: str,
) -> None:
    daily = ROOT / f"json/oracle-{asset}/{asset}_daily_prices.json"
    backup = ROOT / f"json/oracle-{asset}/{asset}_daily_prices_clickhouse_only.json"
    gap_path = ROOT / f"json/oracle-{asset}/{asset}_prices_gap_from_clickhouse.json"
    meta_path = ROOT / f"json/oracle-{asset}/{asset}_meta.json"

    _backup_ch_only(daily, backup)
    gap = json.loads(gap_path.read_text(encoding="utf-8"))
    ch_rows = _load_ch_rows(daily, backup)
    onchain_daily = _aggregate_onchain_daily(
        gap,
        forex=forex,
        payment_symbol=payment_symbol,
        subject=subject,
        pair_native=pair_native,
    )
    combined = _merge(ch_rows, onchain_daily)
    daily.write_text(json.dumps(combined, indent=4), encoding="utf-8")

    meta = {
        "asset": asset,
        "pair": f"{pair_native.split('/')[0]}/USD",
        "sources": [
            "clickhouse_oracle",
            f"onchain {pair_native}" + (f" * forex-{forex}" if forex else ""),
        ],
        "record_count": len(combined),
        "first": combined[0]["date"] if combined else None,
        "last": combined[-1]["date"] if combined else None,
        "ch_days": sum(1 for r in combined if r.get("source") == "clickhouse_oracle"),
        "onchain_days": sum(1 for r in combined if r.get("source") == "onchain_oracle"),
        "gap_ticks": gap.get("count"),
        "gap_complete": gap.get("complete"),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(
        f"{asset}: daily={len(combined)} first={meta['first']} last={meta['last']} "
        f"ch={meta['ch_days']} onchain={meta['onchain_days']} "
        f"last_usd={combined[-1]['price_usd'] if combined else None}"
    )


def main() -> None:
    rebuild_asset(
        "tesouro",
        forex="brl",
        payment_symbol="BRZ",
        pair_native="TESOURO/BRZ",
        subject="onchain.AnswerUpdated.TESOURO-BRZ",
    )
    rebuild_asset(
        "ktb",
        forex=None,
        payment_symbol="USD",
        pair_native="KTB/USD",
        subject="onchain.AnswerUpdated.KTB-USD",
    )
    rebuild_asset(
        "gilts",
        forex="gbp",
        payment_symbol="GBP",
        pair_native="GILTS/GBP",
        subject="onchain.AnswerUpdated.GILTS-GBP",
    )

    from oracle_main import run_asset

    for asset in ("tesouro", "ktb", "gilts"):
        print(f"\n==> ranges {asset}")
        run_asset(asset)


if __name__ == "__main__":
    main()
