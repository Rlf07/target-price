import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import seaborn as sns
import os
import json


# === Configurações ===
fee_percent = 0.05
TVL = 100_000

output_volume = 'graphs/brl/volume/7d/'
output_il = 'graphs/brl/IL/7d/'
output_price = 'graphs/brl/price/7d/'
os.makedirs(output_volume, exist_ok=True)
os.makedirs(output_il, exist_ok=True)
os.makedirs(output_price, exist_ok=True)

# === Estilo visual ===
sns.set(style="whitegrid")
plt.rcParams.update({
    'axes.titlesize': 16,
    'axes.labelsize': 13,
    'legend.fontsize': 12,
    'xtick.labelsize': 11,
    'ytick.labelsize': 11
})

# === Caminhos dos arquivos CSV ===
paths = {
    '99%': 'simulations/historic_simulation_il/brl_days_rebalancing/confidence99/shifted_rebalance7d9950.csv',
    '90%': 'simulations/historic_simulation_il/brl_days_rebalancing/confidence90/shifted_rebalance7d9050.csv',
}

# === Carrega os DataFrames ===
dfs = {}
for label, path in paths.items():
    df = pd.read_csv(path)
    df['date_start'] = pd.to_datetime(df['date_start'])
    dfs[label] = df

# === Gráfico individual de cumulative_volum ===
def plot_volume(df, confidence_label):
    # Calcular automaticamente o range a partir do DataFrame
    range_min = df['range_start_min'].iloc[0]
    range_max = df['range_start_max'].iloc[0]
    range_percent = ((range_max / range_min) - 1) * 100
    label_completo = f'Confidence {confidence_label} | Range ±{range_percent:.1f}%'

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(df['date_start'], df['cumulative_volum'], label=label_completo, color='steelblue', linewidth=2)

    # Título principal com token, fee e TVL
    ax.set_title(f'BRL — Cumulative Volum — Fee: {fee_percent:.2f}%, TVL: ${TVL:,.0f}', fontsize=12)
    
    ax.set_xlabel('Date')
    ax.set_ylabel('Cumulative Volum (USD)')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    fig.autofmt_xdate()
    ax.legend()

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    filename = f"{output_volume}volume_rebalance_{confidence_label.replace('%', '')}.png"
    plt.savefig(filename)
    plt.close()
    print(f"Gráfico individual salvo em: {filename}")


# === Gráfico comparativo de cumulative_volum ===
def plot_comparativo_volum(dfs_dict):
    fig, ax = plt.subplots(figsize=(12, 6))
    cores = {'90%': 'darkorange', '99%': 'steelblue'}

    for label, df in dfs_dict.items():
        # Calcula o range com base no primeiro valor do DataFrame
        range_min = df['range_start_min'].iloc[0]
        range_max = df['range_start_max'].iloc[0]
        range_percent = ((range_max / range_min) - 1) * 100
        label_completo = f'{label} | Range {range_percent:.1f}%'

        ax.plot(df['date_start'], df['cumulative_volum'], label=label_completo, color=cores[label], linewidth=2)

    fig.suptitle('Cumulative Volume Comparison — Token: BRZ', fontsize=16, y=1.05)
    ax.set_title(f"BRL - Fee: {fee_percent:.2f}%, TVL: ${TVL:,.0f}", fontsize=12)

    ax.set_xlabel('Date')
    ax.set_ylabel('Cumulative Volume (USD)')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.legend(title='Confidence')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    fig.autofmt_xdate()

    # Adiciona descrição extra no final do gráfico
    ax.text(0.01, -0.2, '* Volume needed to achieve IL and Rebalancing costs.', transform=ax.transAxes,
            fontsize=10, color='gray', ha='left')

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    filename = f"{output_volume}volume_rebalance_comparativo.png"
    plt.savefig(filename)
    plt.close()
    print(f"Gráfico comparativo salvo em: {filename}")


# === Gráfico comparativo de cumulative_il_net ===
def plot_comparativo_il(dfs_dict):
    fig, ax = plt.subplots(figsize=(12, 6))
    cores = {'90%': 'darkorange', '99%': 'steelblue'}

    for label, df in dfs_dict.items():
        range_min = df['range_start_min'].iloc[0]
        range_max = df['range_start_max'].iloc[0]
        range_percent = ((range_max / range_min) - 1) * 100
        label_completo = f'{label} | Range {range_percent:.1f}%'

        ax.plot(df['date_start'], df['cumulative_il_net'].abs(), label=label_completo, color=cores[label], linewidth=2)

    fig.suptitle('Cumulative Net Impermanent Loss Comparison — Token: BRZ', fontsize=16, y=1.05)
    ax.set_title(f"BRL - Fee: {fee_percent:.2f}%, TVL: ${TVL:,.0f}", fontsize=12)

    ax.set_xlabel('Date')
    ax.set_ylabel('Cumulative Net IL (USD)')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.legend(title='Confidence')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    fig.autofmt_xdate()

    ax.text(0.01, -0.2, '* Net Impermanent Loss: Cumulative IL per day + Rebalance costs.', transform=ax.transAxes,
            fontsize=10, color='gray', ha='left')

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    filename = f"{output_il}volume_rebalance_comparativo_il_net.png"
    plt.savefig(filename)
    plt.close()
    print(f"Gráfico de IL positivo salvo em: {filename}")



# === Gráfico do histórico de preço do MXN ===
def plot_price_history(json_path):
    with open(json_path, 'r') as f:
        data = json.load(f)

    df = pd.DataFrame(data)
    df['date'] = pd.to_datetime(df['date'])

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(df['date'], df['price_open'], color='seagreen', linewidth=2)

    fig.suptitle('Price History — Token: BRZ', fontsize=16, y=1.05)
    ax.set_title(f"BRZ Price", fontsize=12)
    ax.set_xlabel('Date')
    ax.set_ylabel('Price')
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    fig.autofmt_xdate()

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    filename = f"{output_price}price_history.png"
    plt.savefig(filename)
    plt.close()
    print(f"Gráfico de preço salvo em: {filename}")


def plot_day_volume_expected_individual_line(df, confidence_label, color):
    fig, ax = plt.subplots(figsize=(14, 6))

    # Cálculo automático do range
    range_min = df['range_start_min'].iloc[0]
    range_max = df['range_start_max'].iloc[0]
    range_percent = ((range_max / range_min) - 1) * 100
    label_completo = f'Confidence {confidence_label} | Range ±{range_percent:.1f}%'

    # Linha principal
    ax.plot(df['date_start'], df['day_volum_expected'], color=color, linewidth=2, label=label_completo)

    # Média
    media = df['day_volum_expected'].mean()
    ax.axhline(media, color='gray', linestyle='--', linewidth=1.5, label=f'Daily Average ≈ ${media:,.0f}')

    # Título e layout
    ax.set_title(f'BRZ — Fee: {fee_percent:.2f}%, TVL: ${TVL:,.0f}', fontsize=16, y=1.05)
    ax.set_xlabel('Date')
    ax.set_ylabel('Day Volume (USD)')
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    fig.autofmt_xdate()
    ax.legend()

    ax.text(0.01, -0.2, '* Day Volume needed to achieve IL and Rebalancing costs.', transform=ax.transAxes,
            fontsize=10, color='gray', ha='left')

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    filename = f"{output_volume}day_volum_necessary_{confidence_label.replace('%', '')}.png"
    plt.savefig(filename)
    plt.close()
    print(f"Gráfico de linha day_volume_necessary ({confidence_label}) salvo em: {filename}")




# === Execução ===
plot_volume(dfs['99%'], '99%')
plot_volume(dfs['90%'], '90%')
plot_comparativo_volum(dfs)
plot_comparativo_il(dfs)
plot_day_volume_expected_individual_line(dfs['90%'], '90%', 'darkorange')
plot_day_volume_expected_individual_line(dfs['99%'], '99%', 'steelblue')
plot_price_history('json/forex-brl/brl_daily_prices.json')

