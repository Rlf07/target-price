import json
import pandas as pd
import numpy as np
from math import exp, sqrt

# === Configurações do modelo ===
Z_SCORE = 2.576  # (ex: 2.576 = 99%,   1.645 = 90%)
T_EM_DIAS = 2
T_ANO = T_EM_DIAS / 365

# === Proporção da faixa abaixo do price_open (ex: 0.3 = 30% para baixo e 70% para cima) ===
alpha = 0.35

# === Funções auxiliares ===
def calcular_faixa(p0, sigma, z, t):
    fator = z * sigma * sqrt(t)
    min_price = p0 * exp(-fator)
    max_price = p0 * exp(fator)
    return pd.Series([min_price, max_price])

def deslocar_faixa(p0, min_old, max_old, alpha):
    delta = max_old - min_old
    min_new = p0 - alpha * delta
    max_new = p0 + (1 - alpha) * delta
    return pd.Series([min_new, max_new])

# === Carregar os dados ===
with open('json/forex-brl/brl_daily_prices.json', 'r') as f:
    data = json.load(f)

df = pd.DataFrame(data)
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values('date').reset_index(drop=True)

# === Cálculo de log-return e volatilidade anualizada ===
df['log_return'] = np.log(df['price_vwap'] / df['price_vwap'].shift(1))
vol_hist_anual = df['log_return'].std() * sqrt(365)
print(f"Volatilidade histórica anualizada: {vol_hist_anual:.4%}")

# === Faixa esperada (centralizada) ===
df[['price_min_expected', 'price_max_expected']] = df['price_vwap'].apply(
    lambda p: calcular_faixa(p, vol_hist_anual, Z_SCORE, T_ANO)
)

# === Faixa deslocada com proporção assimétrica ===
df[['price_min_shifted', 'price_max_shifted']] = df.apply(
    lambda row: deslocar_faixa(row['price_vwap'], row['price_min_expected'], row['price_max_expected'], alpha),
    axis=1
)

# === Visualizar últimas linhas com tudo ===
print(df[['date', 'price_vwap', 'price_min_expected', 'price_max_expected',
          'price_min_shifted', 'price_max_shifted']].tail())

# === Salvar no CSV final ===
df.to_csv('expected_ranges/brl/2days_brl_expected_range_with_vol99_shifted65.csv', index=False)
