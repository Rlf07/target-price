import pandas as pd
import matplotlib.pyplot as plt
import os

# olhar os caminhos, ainda tem que produzir os resultados com 50 50 e para 99 de grau de confiança
# === Configurações ===
file_7030 = 'simulations/historic_simulation_il/brl_days_rebalancing/confidence9030/shifted_rebalance1d9030.csv'
file_5050 = 'simulations/historic_simulation_il/brl_days_rebalancing/confidence9050/shifted_rebalance7d9050.csv'
output_path = 'graphs/brl/comparative7d/'

# Criar pasta de saída se não existir
os.makedirs(output_path, exist_ok=True)

# === Carregar os dados ===
df_7030 = pd.read_csv(file_7030, parse_dates=['date_start'])
df_5050 = pd.read_csv(file_5050, parse_dates=['date_start'])

# === Garantir que as datas estejam ordenadas ===
df_7030 = df_7030.sort_values(by='date_start')
df_5050 = df_5050.sort_values(by='date_start')

# === Gráfico 1: Cumulative Rebalance Cost ===
fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(df_7030['date_start'], df_7030['cumulative_rebalance_cost'],
        label='BRL - 70% USDC / 30% BRL', color='blue')
ax.plot(df_5050['date_start'], df_5050['cumulative_rebalance_cost'],
        label='BRL - 50% USDC / 50% BRL', color='green')
ax.set_xlabel('Date')
ax.set_ylabel('Cumulative Rebalance Cost (USD)')
ax.set_title('BRL - Comparative: Cumulative Rebalance Cost')
ax.legend()
ax.grid(True)
plt.figtext(0.5, 0.01, 'With rebalance of 7 in 7 days.', ha='center', fontsize=9, color='gray')
plt.tight_layout(rect=[0, 0.03, 1, 1])  # Ajuste para não cortar o texto
plt.savefig(os.path.join(output_path, 'cumulative_rebalance_cost_comparison.png'))
plt.close()

# === Gráfico 2: Cumulative IL (em valor absoluto) ===
fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(df_7030['date_start'], df_7030['cumulative_il'].abs(),
        label='BRL - 70% USDC / 30% BRL', color='blue')
ax.plot(df_5050['date_start'], df_5050['cumulative_il'].abs(),
        label='BRL - 50% USDC / 50% BRL', color='green')
ax.set_xlabel('Date')
ax.set_ylabel('Cumulative IL (USD)')
ax.set_title('BRL - Comparative: Cumulative Impermanent Loss (abs)')
ax.legend()
ax.grid(True)
plt.figtext(0.5, 0.01, 'With rebalance of 7 in 7 days.', ha='center', fontsize=9, color='gray')
plt.tight_layout(rect=[0, 0.03, 1, 1])
plt.savefig(os.path.join(output_path, 'cumulative_il_comparison.png'))
plt.close()
