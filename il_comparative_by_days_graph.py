import os
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
import seaborn as sns

sns.set(style="whitegrid")

def carregar_dados_rebalanceamento(confidence: int, dias_range=range(1, 8)):
    base_path = f"simulations/historic_simulation_il/brl_days_rebalancing/confidence{confidence}30"
    dados_por_periodo = []

    for dias in dias_range:
        filename = f"shifted_rebalance{dias}d{confidence}30.csv"
        filepath = os.path.join(base_path, filename)

        if not os.path.isfile(filepath):
            print(f"[AVISO] Arquivo não encontrado: {filepath}")
            continue

        try:
            df = pd.read_csv(filepath, parse_dates=["date_start"])
            df["rebalance_days"] = dias
            dados_por_periodo.append(df)
        except Exception as e:
            print(f"[ERRO] Falha ao ler {filepath}: {e}")

    if not dados_por_periodo:
        print(f"[ERRO] Nenhum dado válido encontrado para confiança {confidence}%")
        return None

    return pd.concat(dados_por_periodo, ignore_index=True)

def plot_rebalance_costs(df, confidence: int, output_path: str):
    plt.figure(figsize=(12, 6))

    for dias in sorted(df["rebalance_days"].unique()):
        dados_dia = df[df["rebalance_days"] == dias]
        plt.plot(dados_dia["date_start"], dados_dia["cumulative_il_net"].abs(), label=f"{dias}d")

    # Calcular range percentual do último valor
    df_ultimo = df[df["date_start"] == df["date_start"].max()]
    if not df_ultimo.empty:
        range_low = df_ultimo["range_start_min"].values[-1]
        range_high = df_ultimo["range_start_max"].values[-1]
        try:
            range_percent = ((range_high / range_low) - 1) * 100
            range_text = f"Price range: {range_percent:.2f}%"
        except ZeroDivisionError:
            range_text = "Price range: inválido (divisão por zero)"
    else:
        range_text = "Expected price range: dados ausentes"

    plt.annotate(
        range_text,
        xy=(1, 1),
        xycoords='axes fraction',
        ha='right',
        va='bottom',
        fontsize=10,
        bbox=dict(boxstyle="round,pad=0.3", fc="lightyellow", ec="gray", lw=1)
    )

    plt.title(f"BRL Cumulative Net Impermanent Loss - Confidence {confidence}%")
    plt.xlabel("Date Start")
    plt.ylabel("Net Impermanent Loss Absolute (USD)")
    plt.legend(title="Rebalance Every")
    plt.gca().xaxis.set_major_formatter(DateFormatter("%Y-%m-%d"))
    plt.xticks(rotation=45)
    plt.tight_layout()

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    plt.savefig(output_path)
    print(f"[✅] Gráfico salvo em: {output_path}")
    plt.close()

def main():
    confidence_levels = [90, 99]
    output_dir = "graphs/brl/net_il_by_confidence/"
    caminhos_criados = []

    for confidence in confidence_levels:
        df = carregar_dados_rebalanceamento(confidence)

        if df is not None:
            output_file = os.path.join(output_dir, f"net_il_confidence{confidence}.png")
            plot_rebalance_costs(df, confidence, output_file)
            caminhos_criados.append(output_file)

    if caminhos_criados:
        print("\n=== Gráficos criados com sucesso ===")
        for caminho in caminhos_criados:
            print(f"✔ {caminho}")
    else:
        print("\n⚠ Nenhum gráfico foi gerado.")

if __name__ == "__main__":
    main()
