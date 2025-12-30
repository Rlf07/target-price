import pandas as pd
import matplotlib.pyplot as plt
import os

# === Configurações ===
input_path = "simulations/simulations.csv"
output_dir = "simulations/plots"
os.makedirs(output_dir, exist_ok=True)

# === Carregar dados ===
df = pd.read_csv(input_path)

# 🔧 Corrigir a tipagem do 'price'
df["price"] = df["price"].astype(float)

# Calcular valores em USD
df["value_token0_usd"] = df["amount0"] * df["price"]
df["value_token1_usd"] = df["amount1"]
df["total_value_usd"] = df["value_token0_usd"] + df["value_token1_usd"]

# Ordenar por preço para visualização correta
df.sort_values("price", inplace=True)

# Criar diretório para plots
output_dir = "simulations/plots"
os.makedirs(output_dir, exist_ok=True)

# Gráfico: barras empilhadas de valor em USD por token, ao longo do preço
plt.figure(figsize=(12, 6))
plt.bar(df["price"], df["value_token0_usd"], label="Token0 (USD)", color="skyblue", width=0.00001)
plt.bar(df["price"], df["value_token1_usd"], bottom=df["value_token0_usd"], label="Token1 (USD)", color="lightgreen", width=0.00001)

plt.xlabel("Preço")
plt.ylabel("Valor total da posição (USD)")
plt.title("Distribuição de valor entre Token0 e Token1 ao longo do preço")
plt.legend()
plt.grid(True, linestyle="--", alpha=0.4)
plt.tight_layout()

# Salvar e mostrar
plt.savefig(f"{output_dir}/stacked_token_values.png", dpi=300)
plt.show()
# === Gráfico 2: Impermanent Loss Absoluto por price ===
plt.figure(figsize=(10, 6))
plt.plot(df["price"], df["Absolute impermanent loss value"], label="IL Absoluto", color="red", linewidth=2)
plt.xlabel("Preço")
plt.ylabel("IL Absoluto (USD)")
plt.title("Impermanent Loss Absoluto ao longo do preço")
plt.axhline(0, color="gray", linestyle="--", linewidth=1)
plt.grid(True, linestyle="--", alpha=0.4)
plt.tight_layout()
plt.savefig(f"{output_dir}/il_absolute_by_price.png", dpi=300)
plt.show()
