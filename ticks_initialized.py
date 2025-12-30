from web3 import Web3
import json
import os

# === CONFIGURAÇÃO RPC ===
ARBITRUM_RPC = "https://arb1.arbitrum.io/rpc"  # ou use seu RPC privado
web3 = Web3(Web3.HTTPProvider(ARBITRUM_RPC))

# === ENDEREÇO DO CONTRATO DA POOL ===
POOL_ADDRESS = Web3.to_checksum_address("0xc664db6E6f902d5C1Acf73C659B95E4779CAedDE")

# === CARREGAR ABI ===
with open("abis/pool_abi.json", "r") as f:
    pool_abi = json.load(f)

pool = web3.eth.contract(address=POOL_ADDRESS, abi=pool_abi)

# === OBTER SLOT0 E TICK SPACING ===
slot0 = pool.functions.slot0().call()
tick_atual = slot0[1]  # segundo valor do slot0 é o tick
tick_spacing = pool.functions.tickSpacing().call()

print(f"Tick atual: {tick_atual}")
print(f"Tick spacing: {tick_spacing}")

# === FUNÇÃO PARA CONSULTAR UM TICK ===
def get_tick_data(tick):
    try:
        data = pool.functions.ticks(tick).call()
        liquidityGross = data[0]
        liquidityNet = data[1]
        return {"liquidityGross": liquidityGross, "liquidityNet": liquidityNet}
    except:
        return {"liquidityGross": 0, "liquidityNet": 0}

# === FUNÇÃO PARA ACHAR INTERVALO ATIVO ===
def find_active_liquidity_range(tick_atual, tick_spacing, max_ticks=500):
    tick_search = tick_atual - (tick_atual % tick_spacing)

    # Buscar tickLower
    tick_lower = None
    for i in range(max_ticks):
        tick = tick_search - i * tick_spacing
        data = get_tick_data(tick)
        if data["liquidityGross"] > 0:
            tick_lower = tick
            break

    # Buscar tickUpper
    tick_upper = None
    for i in range(1, max_ticks):
        tick = tick_search + i * tick_spacing
        data = get_tick_data(tick)
        if data["liquidityNet"] != 0:
            tick_upper = tick
            break

    return tick_lower, tick_upper

# === APLICAR FUNÇÃO ===
tick_lower, tick_upper = find_active_liquidity_range(tick_atual, tick_spacing)

print(f"Tick com liquidez ativa: {tick_lower} → {tick_upper}")
