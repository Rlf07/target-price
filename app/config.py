from pathlib import Path


DEFAULT_Z_SCORE = 2.576
DEFAULT_ALPHA = 0.5
DEFAULT_HORIZONS = [2, 7, 14, 30]

SUPPORTED_ASSETS = {"brl", "gbp", "idr", "krw", "sgd", "eur", "hkd", "mxn", "aud"}

ASSET_PAIR_LABELS = {
    "brl": ("BRZ", "Brz"),
    "gbp": ("GBP", "Gbp"),
    "idr": ("IDR", "Idr"),
    "aud": ("AUDF", "Audf"),
    "krw": ("KRW", "Krw"),
    "sgd": ("SGD", "Sgd"),
    "eur": ("EUR", "Eur"),
    "hkd": ("HKD", "Hkd"),
    "mxn": ("MXN", "Mxn"),
}


def json_path_for_asset(asset: str) -> Path:
    asset = asset.lower()
    if asset == "mxn":
        return Path(f"json/forex-{asset}/daily_prices.json")
    return Path(f"json/forex-{asset}/{asset}_daily_prices.json")
