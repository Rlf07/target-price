from pathlib import Path


DEFAULT_Z_SCORE = 2.576
DEFAULT_ALPHA = 0.5
DEFAULT_HORIZONS = [2, 7, 14, 30]

FOREX_ASSETS = {"brl", "gbp", "idr", "krw", "sgd", "eur", "hkd", "mxn", "aud", "cad", "zar"}
ORACLE_ASSETS = {"tesouro", "ktb", "gilts"}
SUPPORTED_ASSETS = FOREX_ASSETS | ORACLE_ASSETS

# Mínimo de retornos diários antes de estimar vol para bonds (histórico curto).
ORACLE_MIN_VOL_PERIODS = 14

ASSET_PAIR_LABELS = {
    "brl": ("BRZ", "Brz"),
    "gbp": ("GBP", "Gbp"),
    "idr": ("IDR", "Idr"),
    "aud": ("AUDF", "Audf"),
    "cad": ("CADD", "Cadd"),
    "krw": ("KRW", "Krw"),
    "sgd": ("SGD", "Sgd"),
    "eur": ("EUR", "Eur"),
    "hkd": ("HKD", "Hkd"),
    "mxn": ("MXN", "Mxn"),
    "zar": ("ZARP", "Zarp"),
    "tesouro": ("TESOURO", "Tesouro"),
    "ktb": ("KTB", "Ktb"),
    "gilts": ("GILTS", "Gilts"),
}


def is_oracle_asset(asset: str) -> bool:
    return asset.lower() in ORACLE_ASSETS


def json_path_for_asset(asset: str) -> Path:
    asset = asset.lower()
    if is_oracle_asset(asset):
        return Path(f"json/oracle-{asset}/{asset}_daily_prices.json")
    if asset == "mxn":
        return Path(f"json/forex-{asset}/daily_prices.json")
    return Path(f"json/forex-{asset}/{asset}_daily_prices.json")
