from __future__ import annotations

from math import sqrt

import pandas as pd

from app.config import ORACLE_MIN_VOL_PERIODS


def compute_forex_annual_vol(log_returns: pd.Series) -> float:
    """Vol anualizada usando toda a série (forex com histórico longo)."""
    return float(log_returns.std() * sqrt(365))


def compute_expanding_annual_vol(
    log_returns: pd.Series,
    min_periods: int = ORACLE_MIN_VOL_PERIODS,
) -> pd.Series:
    """
    Vol anualizada em janela expansiva: cada dia usa só o histórico até ali.
    Conforme o feed cresce, a estimativa na última linha usa mais dados.
    """
    return log_returns.expanding(min_periods=min_periods).std() * sqrt(365)


def attach_annual_vol(
    df: pd.DataFrame,
    log_returns: pd.Series,
    is_oracle: bool,
) -> tuple[pd.DataFrame, float, dict]:
    """Attach vol_hist_anual column and metadata about the estimate."""
    n_returns = int(log_returns.notna().sum())

    if is_oracle:
        min_periods = ORACLE_MIN_VOL_PERIODS
        df["vol_hist_anual"] = compute_expanding_annual_vol(
            log_returns, min_periods=min_periods
        )
        latest_vol = df["vol_hist_anual"].iloc[-1]
        if pd.isna(latest_vol):
            raise ValueError(
                f"Histórico insuficiente para vol oracle: {n_returns} retornos diários; "
                f"mínimo {min_periods}."
            )
        meta = {
            "vol_method": "expanding",
            "sample_days": n_returns,
            "min_vol_periods": min_periods,
        }
        return df, float(latest_vol), meta

    vol_scalar = compute_forex_annual_vol(log_returns)
    df["vol_hist_anual"] = vol_scalar
    meta = {
        "vol_method": "full_sample",
        "sample_days": n_returns,
        "min_vol_periods": None,
    }
    return df, vol_scalar, meta
