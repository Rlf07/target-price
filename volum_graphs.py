import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import seaborn as sns
import os
import json
import argparse
import sys
import glob
import itertools
import re


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

# === Detect token / days / sim root via argumentos (ou defaults) ===
parser = argparse.ArgumentParser()
parser.add_argument("--token", type=str, required=False, default="brl",
                    help="Nome do token (ex: brl, eur, mxn)")
parser.add_argument("--days", type=int, required=False, default=7,
                    help="Número de dias de rebalance (ex: 7)")
parser.add_argument("--sim_root", type=str, required=False, default="simulations",
                    help="Pasta raiz onde estão os resultados (default: 'simulations')")
args = parser.parse_args()

token = args.token.lower()
days = args.days
sim_root = args.sim_root

# === Output folders automáticos por token / days ===
output_volume = f'graphs/{token}/volume/{days}d/'
output_il = f'graphs/{token}/IL/{days}d/'
output_price = f'graphs/{token}/price/{days}d/'
os.makedirs(output_volume, exist_ok=True)
os.makedirs(output_il, exist_ok=True)
os.makedirs(output_price, exist_ok=True)


# === Função para encontrar os CSVs de simulação correspondentes ===
def find_simulation_files(token, days, sim_root="simulations"):
    base_dir = os.path.join(sim_root, "historic_simulation_il", f"{token}_days_rebalancing")
    pattern = os.path.join(base_dir, "confidence*", f"shifted_rebalance{days}d*.csv")
    matched = sorted(glob.glob(pattern))
    results = {}
    for fpath in matched:
        fname = os.path.basename(fpath)
        m = re.match(
            rf"shifted_rebalance{days}d(?P<conf>\d{{2}})(?P<perc>\d{{2}})_(?P<rangetag>using_shifted|using_expected)\.csv",
            fname
        )
        if m:
            conf = m.group("conf")
            perc = m.group("perc")
            rangetag = m.group("rangetag")
        else:
            parent = os.path.basename(os.path.dirname(fpath))
            m2 = re.match(r"confidence(?P<conf>\d{2})(?P<perc>\d{2})", parent)
            if m2:
                conf = m2.group("conf")
                perc = m2.group("perc")
            else:
                conf = "unk"
                perc = ""
            rangetag = "using_shifted" if "using_shifted" in fname else (
                "using_expected" if "using_expected" in fname else "unknown"
            )

        label = f"{conf}% confidence {perc}% shifted | {rangetag.replace('using_','')}"
        if label in results:  # evita duplicados
            suffix = 1
            while f"{label}#{suffix}" in results:
                suffix += 1
            label = f"{label}#{suffix}"
        results[label] = fpath
    return results


# === Descobre arquivos e carrega DataFrames automaticamente ===
paths = find_simulation_files(token, days, sim_root)
if not paths:
    print(f"⚠️  Nenhum arquivo encontrado para token='{token}', days={days} em {sim_root}/{token}_days_rebalancing")
    sys.exit(1)

dfs = {}
for label, path in paths.items():
    df = pd.read_csv(path)
    # garante datetime
    if "date_start" in df.columns:
        df['date_start'] = pd.to_datetime(df['date_start'])
    elif "date" in df.columns:
        df['date_start'] = pd.to_datetime(df['date'])
    dfs[label] = df

print(f"🟢 Encontrados {len(dfs)} arquivos para token '{token}' com window {days}d")
for lbl, p in paths.items():
    print(f"  - {lbl} -> {p}")

def sanitize_filename(s):
    # Remove ou substitui caracteres inválidos para arquivos
    s = re.sub(r'[<>:"/\\|?*%]', '_', s)
    s = s.replace(' ', '_')  # opcional: trocar espaços por underscore
    return s

# === Gráfico individual de cumulative_volum ===
def plot_volume(df, confidence_label, token):
    # Calcular automaticamente o range a partir do DataFrame
    range_min = df['range_start_min'].iloc[0]
    range_max = df['range_start_max'].iloc[0]
    range_percent = ((range_max / range_min) - 1) * 100
    label_completo = f'{label} | Range ±{range_percent:.1f}%'

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(df['date_start'], df['cumulative_volum'], label=label_completo, color='steelblue', linewidth=2)

    # Título principal com token, fee e TVL
    ax.set_title(f'{token.upper()} — Cumulative Volume — Fee: {fee_percent:.2f}%, TVL: ${TVL:,.0f}', fontsize=12)
    
    ax.set_xlabel('Date')
    ax.set_ylabel('Cumulative Volum (USD)')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    fig.autofmt_xdate()
    ax.legend()

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    filename = f"{output_volume}volume_rebalance_{sanitize_filename(confidence_label)}.png"
    plt.savefig(filename)
    plt.close()
    print(f"Gráfico individual salvo em: {filename}")


# === Gráfico comparativo de cumulative_volum ===
def plot_comparativo_volum(dfs_dict, token):
    fig, ax = plt.subplots(figsize=(12, 6))
    color_cycle = itertools.cycle(['steelblue', 'darkorange', 'seagreen', 'purple', 'gray'])

    for label, df in dfs_dict.items():
        color = next(color_cycle)
        # Calcula o range com base no primeiro valor do DataFrame
        range_min = df['range_start_min'].iloc[0]
        range_max = df['range_start_max'].iloc[0]
        range_percent = ((range_max / range_min) - 1) * 100
        label_completo = f'{label} | Range ±{range_percent:.1f}%'

        ax.plot(df['date_start'], df['cumulative_volum'], label=label_completo, color=color, linewidth=2)

    fig.suptitle(f'Cumulative Volume Comparison — Token: {token.upper()}', fontsize=16, y=1.05)
    ax.set_title(f"{token.upper()} - Fee: {fee_percent:.2f}%, TVL: ${TVL:,.0f}", fontsize=12)

    ax.set_xlabel('Date')
    ax.set_ylabel('Cumulative Volume (USD)')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.legend(title='Confidence / Shift')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    fig.autofmt_xdate()

    ax.text(0.01, -0.2, '* Volume needed to achieve IL and Rebalancing costs.', transform=ax.transAxes,
            fontsize=10, color='gray', ha='left')

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    filename = f"{output_volume}volume_rebalance_comparativo.png"
    plt.savefig(filename)
    plt.close()
    print(f"Gráfico comparativo salvo em: {filename}")



# === Gráfico comparativo de cumulative_il_net ===
def plot_comparativo_il(dfs_dict, token):
    fig, ax = plt.subplots(figsize=(12, 6))
    color_cycle = itertools.cycle(['steelblue', 'darkorange', 'seagreen', 'purple', 'gray'])

    for label, df in dfs_dict.items():
        color = next(color_cycle)
        range_min = df['range_start_min'].iloc[0]
        range_max = df['range_start_max'].iloc[0]
        range_percent = ((range_max / range_min) - 1) * 100
        label_completo = f'{label} | Range ±{range_percent:.1f}%'

        ax.plot(df['date_start'], df['cumulative_il_net'].abs(), label=label_completo, color=color, linewidth=2)

    fig.suptitle(f'Cumulative Net Impermanent Loss Comparison — Token: {token.upper()}', fontsize=16, y=1.05)
    ax.set_title(f"{token.upper()} - Fee: {fee_percent:.2f}%, TVL: ${TVL:,.0f}", fontsize=12)

    ax.set_xlabel('Date')
    ax.set_ylabel('Cumulative Net IL (USD)')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'${x:,.0f}'))
    ax.grid(True, linestyle='--', alpha=0.6)
    ax.legend(title='Confidence / Shift')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
    fig.autofmt_xdate()

    ax.text(0.01, -0.2, '* Net Impermanent Loss: Cumulative IL per day + Rebalance costs.', transform=ax.transAxes,
            fontsize=10, color='gray', ha='left')

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    filename = f"{output_il}volume_rebalance_comparativo_il_net.png"
    plt.savefig(filename)
    plt.close()
    print(f"Gráfico de IL positivo salvo em: {filename}")




# === Gráfico do histórico de preço ===
def plot_price_history(token):
    json_path = f"json/forex-{token}/{token}_daily_prices.json"
    if not os.path.exists(json_path):
        print(f"⚠️  JSON de preço não encontrado: {json_path} — pulando gráfico de preço.")
        return

    with open(json_path, 'r') as f:
        data = json.load(f)

    df = pd.DataFrame(data)
    # tenta campos comuns
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'])
    elif 'timestamp' in df.columns:
        df['date'] = pd.to_datetime(df['timestamp'], unit='s')

    # escolhe price_open ou price_vwap se existir
    price_col = 'price_vwap' if 'price_vwap' in df.columns else ('price_open' if 'price_open' in df.columns else df.columns[0])

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(df['date'], df[price_col], linewidth=2)

    fig.suptitle(f'Price History — Token: {token.upper()}', fontsize=16, y=1.05)
    ax.set_title(f"{token.upper()} Price ", fontsize=12)
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



def plot_day_volume_expected_individual_line(df, confidence_label, color, token):
    fig, ax = plt.subplots(figsize=(14, 6))

    # Cálculo automático do range
    range_min = df['range_start_min'].iloc[0]
    range_max = df['range_start_max'].iloc[0]
    range_percent = ((range_max / range_min) - 1) * 100
    label_completo = f'{label} | Range ±{range_percent:.1f}%'

    # Linha principal
    ax.plot(df['date_start'], df['day_volum_expected'], color=color, linewidth=2, label=label_completo)

    # Média
    media = df['day_volum_expected'].mean()
    ax.axhline(media, color='gray', linestyle='--', linewidth=1.5, label=f'Daily Average ≈ ${media:,.0f}')

    # Título e layout
    ax.set_title(f'{token.upper()} — Fee: {fee_percent:.2f}%, TVL: ${TVL:,.0f}', fontsize=16, y=1.05)
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
    filename = f"{output_volume}day_volum_necessary_{sanitize_filename(confidence_label)}.png"
    plt.savefig(filename)
    plt.close()
    print(f"Gráfico de linha day_volume_necessary ({confidence_label}) salvo em: {filename}")




# === Execução ===
# plot individual cumulative_volum para cada arquivo
for label, df in dfs.items():
    try:
        plot_volume(df, label, token)
    except Exception as e:
        print(f"Erro ao plotar volume individual ({label}): {e}")

# comparativos
plot_comparativo_volum(dfs, token)
plot_comparativo_il(dfs, token)

# day volume individual (com cores em ciclo)
color_list = ['steelblue', 'darkorange', 'seagreen', 'purple', 'gray']
for i, (label, df) in enumerate(dfs.items()):
    color = color_list[i % len(color_list)]
    try:
        plot_day_volume_expected_individual_line(df, label, color, token)
    except Exception as e:
        print(f"Erro ao plotar day_volum ({label}): {e}")

# preço (JSON)
plot_price_history(token)
