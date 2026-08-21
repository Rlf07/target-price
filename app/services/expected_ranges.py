from __future__ import annotations

from math import exp, sqrt

import numpy as np
import pandas as pd

from app.config import ASSET_PAIR_LABELS, is_oracle_asset
from app.services.volatility import attach_annual_vol


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
    from decimal import Decimal

    if asset == "idr":
        return format(Decimal(str(float(x))), "f")
    return str(float(x))


def build_ranges_for_horizon(
    df_base: pd.DataFrame,
    t_dias: int,
    z_score: float,
    alpha: float,
    is_oracle: bool = False,
) -> pd.DataFrame:
    df = df_base.copy()
    t_ano = t_dias / 365

    df["log_return"] = np.log(df["price_vwap"] / df["price_vwap"].shift(1))
    df, latest_vol, vol_meta = attach_annual_vol(df, df["log_return"], is_oracle=is_oracle)

    def calc_expected(row: pd.Series) -> pd.Series:
        vol = row["vol_hist_anual"]
        if pd.isna(vol):
            return pd.Series([np.nan, np.nan])
        min_p, max_p = _calcular_faixa(
            float(row["price_vwap"]), float(vol), z_score, t_ano
        )
        return pd.Series([min_p, max_p])

    expected = df.apply(calc_expected, axis=1)
    expected.columns = ["price_min_expected", "price_max_expected"]
    df[["price_min_expected", "price_max_expected"]] = expected

    def calc_shifted(row: pd.Series) -> pd.Series:
        if pd.isna(row["price_min_expected"]) or pd.isna(row["price_max_expected"]):
            return pd.Series([np.nan, np.nan])
        min_s, max_s = _deslocar_faixa(
            float(row["price_vwap"]),
            float(row["price_min_expected"]),
            float(row["price_max_expected"]),
            alpha,
        )
        return pd.Series([min_s, max_s])

    shifted = df.apply(calc_shifted, axis=1)
    shifted.columns = ["price_min_shifted", "price_max_shifted"]
    df[["price_min_shifted", "price_max_shifted"]] = shifted

    df["price_min_shifted_inverted"] = 1 / df["price_max_shifted"]
    df["price_max_shifted_inverted"] = 1 / df["price_min_shifted"]
    df["range_percentage"] = (
        (df["price_max_shifted"] - df["price_min_shifted"]) / df["price_vwap"]
    ) * 100

    df.attrs["vol_hist_anual"] = latest_vol
    df.attrs["vol_method"] = vol_meta["vol_method"]
    df.attrs["sample_days"] = vol_meta["sample_days"]
    df.attrs["min_vol_periods"] = vol_meta["min_vol_periods"]
    return df


def compute_expected_ranges(
    asset: str,
    df_history: pd.DataFrame,
    horizons: list[int],
    z_score: float,
    alpha: float,
) -> dict[int, pd.DataFrame]:
    asset = asset.lower()
    oracle = is_oracle_asset(asset)
    df_base = df_history.copy()

    if oracle:
        if "price_usd" not in df_base.columns:
            raise ValueError(f"Oracle asset {asset} requer coluna price_usd no histórico.")
        df_base["price_vwap"] = df_base["price_usd"]
    elif asset == "idr":
        df_base["price_vwap"] = df_base["price_open"]

    results: dict[int, pd.DataFrame] = {}
    for t_dias in sorted(horizons):
        results[t_dias] = build_ranges_for_horizon(
            df_base, t_dias, z_score, alpha, is_oracle=oracle
        )
    return results


def build_summary_payload(
    asset: str,
    results_by_days: dict[int, pd.DataFrame],
    z_score: float,
    alpha: float,
) -> dict:
    asset = asset.lower()
    oracle = is_oracle_asset(asset)
    sym_upper, sym_title = ASSET_PAIR_LABELS.get(asset, (asset.upper(), asset.title()))
    sorted_days = sorted(results_by_days.keys())
    latest_df = results_by_days[sorted_days[0]]
    latest_row_sample = latest_df.iloc[-1]
    date_br = _format_date_br(pd.Timestamp(latest_row_sample["date"]))

    vol_pct = float(latest_df.attrs.get("vol_hist_anual", 0)) * 100
    sample_days = latest_df.attrs.get("sample_days")
    vol_method = latest_df.attrs.get("vol_method")

    results = []
    lines = [
        f"Ativo: {asset.upper()} ({sym_upper})",
        f"Z_SCORE: {z_score} | alpha: {alpha}",
    ]
    if oracle:
        lines.append(
            f"Amostra: {sample_days} dias | vol: {vol_pct:.2f}% ({vol_method}, min {latest_df.attrs.get('min_vol_periods')} obs)"
        )
    lines.append("")
    lines.append(date_br)

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

    payload = {
        "asset": asset,
        "symbol": sym_upper,
        "date": str(pd.Timestamp(latest_row_sample["date"]).date()),
        "z_score": z_score,
        "alpha": alpha,
        "results": results,
        "summary_text": "\n".join(lines).rstrip() + "\n",
    }
    if oracle:
        payload["sample_days"] = sample_days
        payload["vol_method"] = vol_method
        payload["vol_annual_pct"] = vol_pct

    return payload
