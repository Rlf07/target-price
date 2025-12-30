import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

# idr_expected_range_with_vol90_shifted70.csv / idr_expected_range_with_vol99_shifted70.csv
# === 1. Lê os dados ===
df = pd.read_csv('brl_expected_range_with_vol99_shifted50.csv', parse_dates=['date'])

# === 2. Converte colunas para float (garantia)
df['price_min_shifted'] = pd.to_numeric(df['price_min_shifted'], errors='coerce')
df['price_max_shifted'] = pd.to_numeric(df['price_max_shifted'], errors='coerce')
df['price_vwap'] = pd.to_numeric(df['price_vwap'], errors='coerce')

# === 3. Ordena por data de forma explícita
df = df.sort_values('date').reset_index(drop=True)

# === 4. Agora sim, pega a última linha cronológica
last_row = df[df['date'] == df['date'].max()].iloc[0]
last_min = last_row['price_min_shifted']
last_max = last_row['price_max_shifted']
last_date = last_row['date']

# === 5. Plota
plt.figure(figsize=(12, 6))

# VWAP no tempo
plt.plot(df['date'], df['price_vwap'], label='Historical Price - 99% confidence', color='blue', linewidth=2)

# Linhas horizontais com a última faixa estimada
plt.axhline(y=last_min, color='red', linestyle='--', label=f'Min Price Target ({last_min:.8f})')
plt.axhline(y=last_max, color='green', linestyle='--', label=f'Mex Price Target ({last_max:.8f})')

# Estética
plt.title(f'BRL - Historical Price (Dates: {last_date.date()})', fontsize=14)
plt.xlabel('Date')
plt.ylabel('Price')
plt.gca().yaxis.set_major_formatter(mticker.FormatStrFormatter('%.8f'))
plt.grid(True, linestyle=':', alpha=0.7)
plt.legend()
plt.tight_layout()

print(last_row)
print("Última data:", df['date'].max())
print("Faixa da última data:", last_min, last_max)


plt.show()
