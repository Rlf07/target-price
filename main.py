import json
from pathlib import Path
from math import exp, sqrt
from decimal import Decimal

import numpy as np
import pandas as pd

# === Configuração única do ativo e do modelo ===
ASSET = "gbp"  # ex: brl, gbp, idr, krw, sgd, eur, hkd, mxn, aud

Z_SCORE = 2.576  # ex: 2.576 ≈ 99%, 1.645 ≈ 90%
alpha = 0.5  # proporção da faixa abaixo do price_vwap (0.5 = 50%)

# Horizontes (dias) processados em uma única execução
T_EM_DIAS_LIST = [2, 7, 14, 30]

# Par exibido no relatório (token alvo / USDC)
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
        return Path("json/forex-mxn/daily_prices.json")
    return Path(f"json/forex-{asset}/{asset}_daily_prices.json")


def expected_ranges_dir(asset: str) -> Path:
    return Path("expected_ranges") / asset.lower()


def z_filename_token(z: float) -> str:
    """Identificador compacto do z-score para nome de arquivo (ex: 2.576 → z2576)."""
    return f"z{int(round(z * 1000))}"


def alpha_filename_token(a: float) -> str:
    """ex: 0.5 → alpha50, 0.7 → alpha70."""
    return f"alpha{int(round(a * 100))}"


def csv_basename(days: int, asset: str) -> str:
    zt = z_filename_token(Z_SCORE)
    at = alpha_filename_token(alpha)
    return f"{days}days_{asset.lower()}_expected_range_{zt}_{at}.csv"


def calcular_faixa(p0, sigma, z, t):
    fator = z * sigma * sqrt(t)
    min_price = p0 * exp(-fator)
    max_price = p0 * exp(fator)
    return pd.Series([min_price, max_price])


def deslocar_faixa(p0, min_old, max_old, a):
    delta = max_old - min_old
    min_new = p0 - a * delta
    max_new = p0 + (1 - a) * delta
    return pd.Series([min_new, max_new])


def load_price_frame(asset: str) -> pd.DataFrame:
    path = json_path_for_asset(asset)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def build_ranges_for_horizon(df_base: pd.DataFrame, t_dias: int) -> pd.DataFrame:
    df = df_base.copy()
    t_ano = t_dias / 365
    df["log_return"] = np.log(df["price_vwap"] / df["price_vwap"].shift(1))
    vol_hist_anual = df["log_return"].std() * sqrt(365)

    df[["price_min_expected", "price_max_expected"]] = df["price_vwap"].apply(
        lambda p: calcular_faixa(p, vol_hist_anual, Z_SCORE, t_ano)
    )
    df[["price_min_shifted", "price_max_shifted"]] = df.apply(
        lambda row: deslocar_faixa(
            row["price_vwap"],
            row["price_min_expected"],
            row["price_max_expected"],
            alpha,
        ),
        axis=1,
    )
    df["price_min_shifted_inverted"] = 1 / df["price_max_shifted"]
    df["price_max_shifted_inverted"] = 1 / df["price_min_shifted"]
    df["range_percentage"] = (
        (df["price_max_shifted"] - df["price_min_shifted"]) / df["price_vwap"]
    ) * 100

    df.attrs["vol_hist_anual"] = vol_hist_anual
    df.attrs["t_em_dias"] = t_dias
    return df


def format_date_br(d) -> str:
    if hasattr(d, "day"):
        return f"{d.day}/{d.month:02d}/{d.year}"
    ts = pd.Timestamp(d)
    return f"{ts.day}/{ts.month:02d}/{ts.year}"


def write_summary_report(
    asset: str,
    results_by_days: dict[int, pd.DataFrame],
    out_path: Path,
) -> None:
    sym_upper, sym_title = ASSET_PAIR_LABELS.get(
        asset.lower(), (asset.upper(), asset.title())
    )

    def fmt_price(x) -> str:
        # Para IDR o price é muito pequeno e aparece como e-05; aqui removemos notação científica.
        if asset.lower() == "idr":
            return format(Decimal(str(float(x))), "f")
        return str(x)

    lines: list[str] = []
    lines.append(f"Ativo: {asset.upper()} ({sym_upper})")
    lines.append(f"Z_SCORE: {Z_SCORE} | alpha: {alpha}")
    lines.append("")

    sorted_days = sorted(results_by_days.keys())
    # Data mais recente uma vez (mesma base para todos os horizontes)
    latest_row_sample = results_by_days[sorted_days[0]].iloc[-1]
    lines.append(format_date_br(latest_row_sample["date"]))

    for t_dias in sorted_days:
        df = results_by_days[t_dias]
        row = df.iloc[-1]
        vwap = row["price_vwap"]
        rp = row["range_percentage"]
        lines.append(f"{t_dias} rebalancing")
        lines.append(f"{sym_upper} ranges para o price {fmt_price(vwap)} (range {rp:.2f}%)")
        lines.append("")
        lines.append(f"{sym_title}/usdc -")
        lines.append(f"Lower = {fmt_price(row['price_min_shifted_inverted'])}")
        lines.append(f"Upper = {fmt_price(row['price_max_shifted_inverted'])}")
        lines.append("")
        lines.append(f"Usdc/{asset.lower()}")
        lines.append(f"Lower = {fmt_price(row['price_min_shifted'])}")
        lines.append(f"Upper = {fmt_price(row['price_max_shifted'])}")
        lines.append("")
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def main():
    asset = ASSET.lower()
    json_path = json_path_for_asset(asset)
    if not json_path.is_file():
        raise FileNotFoundError(f"JSON não encontrado: {json_path}")

    out_dir = expected_ranges_dir(asset)
    out_dir.mkdir(parents=True, exist_ok=True)

    df_base = load_price_frame(asset)
    if asset == "idr":
        # A API arredonda o price_vwap para IDR; para os cálculos usamos price_open como referência.
        df_base = df_base.copy()
        df_base["price_vwap"] = df_base["price_open"]
    results_by_days: dict[int, pd.DataFrame] = {}

    for t_dias in T_EM_DIAS_LIST:
        df = build_ranges_for_horizon(df_base, t_dias)
        vol = df.attrs["vol_hist_anual"]
        print(
            f"T_EM_DIAS={t_dias} | Volatilidade histórica anualizada: {vol:.4%}"
        )
        print(
            df[
                [
                    "date",
                    "price_vwap",
                    "price_min_shifted",
                    "price_max_shifted",
                    "price_min_shifted_inverted",
                    "price_max_shifted_inverted",
                    "range_percentage",
                ]
            ].tail(3)
        )

        csv_name = csv_basename(t_dias, asset)
        csv_path = out_dir / csv_name
        df.to_csv(csv_path, index=False)
        print(f"Salvo: {csv_path}\n")
        results_by_days[t_dias] = df

    summary_name = (
        f"rebalancing_summary_{asset}_{z_filename_token(Z_SCORE)}_"
        f"{alpha_filename_token(alpha)}.txt"
    )
    summary_path = out_dir / summary_name
    write_summary_report(asset, results_by_days, summary_path)
    print(f"Resumo: {summary_path}")


if __name__ == "__main__":
    main()
