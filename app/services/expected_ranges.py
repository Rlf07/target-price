from __future__ import annotations

from decimal import Decimal
from math import exp, sqrt

import numpy as np
import pandas as pd

from app.config import ASSET_PAIR_LABELS


def _calcular_faixa(p0: float, sigma: float, z: float, t: float) -> tuple[float, float]:
    fator = z * sigma * sqrt(t)
    min_price = p0 * exp(-fator)
    max_price = p0 * exp(fator)
    return min_price, max_price


def _deslocar_faixa(
    p0: float, min_old: float, max_old: float, alpha: float
) -> tuple[float, float]:
    delta = max_old - min_old
    min_new = p0 - alpha * delta
    max_new = p0 + (1 - alpha) * delta
    return min_new, max_new


def _format_date_br(d: pd.Timestamp) -> str:
    return f"{d.day}/{d.month:02d}/{d.year}"


def _fmt_price(asset: str, x: float) -> str:
    if asset == "idr":
        return format(Decimal(str(float(x))), "f")
    return str(float(x))


def build_ranges_for_horizon(
    df_base: pd.DataFrame, t_dias: int, z_score: float, alpha: float
) -> pd.DataFrame:
    df = df_base.copy()
    t_ano = t_dias / 365

    df["log_return"] = np.log(df["price_vwap"] / df["price_vwap"].shift(1))
    vol_hist_anual = float(df["log_return"].std() * sqrt(365))

    expected = df["price_vwap"].apply(
        lambda p: pd.Series(_calcular_faixa(float(p), vol_hist_anual, z_score, t_ano))
    )
    expected.columns = ["price_min_expected", "price_max_expected"]
    df[["price_min_expected", "price_max_expected"]] = expected

    shifted = df.apply(
        lambda row: pd.Series(
            _deslocar_faixa(
                float(row["price_vwap"]),
                float(row["price_min_expected"]),
                float(row["price_max_expected"]),
                alpha,
            )
        ),
        axis=1,
    )
    shifted.columns = ["price_min_shifted", "price_max_shifted"]
    df[["price_min_shifted", "price_max_shifted"]] = shifted

    df["price_min_shifted_inverted"] = 1 / df["price_max_shifted"]
    df["price_max_shifted_inverted"] = 1 / df["price_min_shifted"]
    df["range_percentage"] = (
        (df["price_max_shifted"] - df["price_min_shifted"]) / df["price_vwap"]
    ) * 100

    df.attrs["vol_hist_anual"] = vol_hist_anual
    return df


def compute_expected_ranges(
    asset: str,
    df_history: pd.DataFrame,
    horizons: list[int],
    z_score: float,
    alpha: float,
) -> dict[int, pd.DataFrame]:
    asset = asset.lower()
    df_base = df_history.copy()
    # Regra de negócio existente: IDR usa price_open por arredondamento de vwap.
    if asset == "idr":
        df_base["price_vwap"] = df_base["price_open"]

    results: dict[int, pd.DataFrame] = {}
    for t_dias in sorted(horizons):
        results[t_dias] = build_ranges_for_horizon(df_base, t_dias, z_score, alpha)
    return results


def build_summary_payload(
    asset: str,
    results_by_days: dict[int, pd.DataFrame],
    z_score: float,
    alpha: float,
) -> dict:
    asset = asset.lower()
    sym_upper, sym_title = ASSET_PAIR_LABELS.get(asset, (asset.upper(), asset.title()))
    sorted_days = sorted(results_by_days.keys())
    latest_row_sample = results_by_days[sorted_days[0]].iloc[-1]
    date_br = _format_date_br(pd.Timestamp(latest_row_sample["date"]))

    results = []
    lines = [
        f"Ativo: {asset.upper()} ({sym_upper})",
        f"Z_SCORE: {z_score} | alpha: {alpha}",
        "",
        date_br,
    ]

    for t_dias in sorted_days:
        row = results_by_days[t_dias].iloc[-1]
        item = {
            "days": t_dias,
            "price_reference": float(row["price_vwap"]),
            "range_percentage": float(row["range_percentage"]),
            "token_usdc": {
                "lower": float(row["price_min_shifted_inverted"]),
                "upper": float(row["price_max_shifted_inverted"]),
            },
            "usdc_token": {
                "lower": float(row["price_min_shifted"]),
                "upper": float(row["price_max_shifted"]),
            },
        }
        results.append(item)

        lines.append(f"{t_dias} rebalancing")
        lines.append(
            f"{sym_upper} ranges para o price {_fmt_price(asset, row['price_vwap'])} "
            f"(range {row['range_percentage']:.2f}%)"
        )
        lines.append("")
        lines.append(f"{sym_title}/usdc -")
        lines.append(f"Lower = {_fmt_price(asset, row['price_min_shifted_inverted'])}")
        lines.append(f"Upper = {_fmt_price(asset, row['price_max_shifted_inverted'])}")
        lines.append("")
        lines.append(f"Usdc/{asset}")
        lines.append(f"Lower = {_fmt_price(asset, row['price_min_shifted'])}")
        lines.append(f"Upper = {_fmt_price(asset, row['price_max_shifted'])}")
        lines.append("")
        lines.append("")

    return {
        "asset": asset,
        "symbol": sym_upper,
        "date": str(pd.Timestamp(latest_row_sample["date"]).date()),
        "z_score": z_score,
        "alpha": alpha,
        "results": results,
        "summary_text": "\n".join(lines).rstrip() + "\n",
    }
