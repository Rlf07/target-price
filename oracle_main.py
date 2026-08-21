"""
Gera expected ranges para ativos oracle (bonds) com histórico curto.

Usa vol em janela expansiva (ver app/services/volatility.py).
Pré-requisito: json/oracle-{asset}/{asset}_daily_prices.json
"""

from pathlib import Path

from app.config import DEFAULT_ALPHA, DEFAULT_HORIZONS, DEFAULT_Z_SCORE, ORACLE_ASSETS
from app.providers.history_provider import load_price_history
from app.services.expected_ranges import build_summary_payload, compute_expected_ranges


def z_filename_token(z: float) -> str:
    return f"z{int(round(z * 1000))}"


def alpha_filename_token(a: float) -> str:
    return f"alpha{int(round(a * 100))}"


def run_asset(asset: str) -> None:
    z_score = DEFAULT_Z_SCORE
    alpha = DEFAULT_ALPHA
    horizons = DEFAULT_HORIZONS

    df = load_price_history(asset, source="local")
    results = compute_expected_ranges(asset, df, horizons, z_score, alpha)

    out_dir = Path("expected_ranges") / asset
    out_dir.mkdir(parents=True, exist_ok=True)

    for t_dias, df_out in results.items():
        vol = df_out.attrs["vol_hist_anual"]
        print(
            f"{asset} | {t_dias}d | amostra={df_out.attrs['sample_days']} | "
            f"vol={vol:.4%} ({df_out.attrs['vol_method']})"
        )
        print(f"  range% última linha: {df_out.iloc[-1]['range_percentage']:.2f}%")

        zt = z_filename_token(z_score)
        at = alpha_filename_token(alpha)
        csv_path = out_dir / f"{t_dias}days_{asset}_expected_range_{zt}_{at}.csv"
        df_out.to_csv(csv_path, index=False)
        print(f"  salvo: {csv_path}")

    summary = build_summary_payload(asset, results, z_score, alpha)
    summary_path = out_dir / (
        f"rebalancing_summary_{asset}_{z_filename_token(z_score)}_"
        f"{alpha_filename_token(alpha)}.txt"
    )
    summary_path.write_text(summary["summary_text"], encoding="utf-8")
    print(f"  resumo: {summary_path}\n")


def main() -> None:
    for asset in sorted(ORACLE_ASSETS):
        print(f"==> {asset}")
        run_asset(asset)


if __name__ == "__main__":
    main()
