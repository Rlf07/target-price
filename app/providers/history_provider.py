from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd

from app.config import json_path_for_asset


def _load_local_history(asset: str) -> pd.DataFrame:
    path = Path(__file__).resolve().parents[2] / json_path_for_asset(asset)
    if not path.is_file():
        raise FileNotFoundError(f"JSON não encontrado para ativo {asset}: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def _load_polygon_history(asset: str, lookback_days: int = 730) -> pd.DataFrame:
    # Import local para evitar acoplamento forte quando o provider online não for usado.
    from src.polygonio import PolygonIo

    end_timestamp = int(time.time())
    start_timestamp = end_timestamp - (lookback_days * 24 * 60 * 60)
    ticker = f"C:{asset.upper()}USD"
    data = PolygonIo.get_daily_prices_between_dates(ticker, start_timestamp, end_timestamp)

    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["timestamp"], unit="s", utc=True).dt.tz_convert(None)
    return df.sort_values("date").reset_index(drop=True)


def load_price_history(
    asset: str, source: str = "auto", lookback_days: int = 730
) -> pd.DataFrame:
    """
    source:
      - polygon: força provider online
      - local: força JSON local
      - auto: tenta polygon e cai para local em caso de erro
    """
    source = source.lower()
    if source not in {"polygon", "local", "auto"}:
        raise ValueError("source inválido. Use: polygon, local, auto")

    if source == "local":
        return _load_local_history(asset)

    if source == "polygon":
        return _load_polygon_history(asset, lookback_days=lookback_days)

    # auto
    try:
        return _load_polygon_history(asset, lookback_days=lookback_days)
    except Exception:
        return _load_local_history(asset)
