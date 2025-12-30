import math
import pandas as pd
import os
import csv

modo = "historico"      # escolher entre simulacao ou historico

def price_to_tick(price):
    return int(math.log(price) / math.log(1.0001))

def tick_to_price(tick):
    return 1.0001 ** tick

def price_to_sqrtX96(price):
    return math.sqrt(price) * 2 ** 96

def sqrtX96_to_price(sqrtPriceX96):
    return (sqrtPriceX96 / 2**96) ** 2

def get_L_and_amounts(value_usd, price, sqrtP, sqrtPLow, sqrtPHigh):
    # term0 = (sqrtPHigh - sqrtP) / (sqrtP * sqrtPLow) * price
    # term1 = sqrtP - sqrtPLow

    # L = value_usd / (term0 + term1)

    # amount0 = L * (sqrtPHigh - sqrtP) / (sqrtP * sqrtPHigh)
    # amount1 = L * (sqrtP - sqrtPLow)

    # return L, amount0, amount1
    if not (sqrtPLow < sqrtP < sqrtPHigh):
        if sqrtP <= sqrtPLow:
            amount0 = value_usd / price
            amount1 = 0
        else:
            amount0 = 0
            amount1 = value_usd
        return 0, amount0, amount1, None, None      # Padrao com 5 valores
    
    term0 = (sqrtPHigh - sqrtP) / (sqrtP * sqrtPHigh)
    term1 = sqrtP - sqrtPLow

    L = value_usd / (term0 * price + term1)

    amount0 = L * term0
    amount1 = L * term1

    return L, amount0, amount1, term0, term1

def nearest_valid_tick(tick, tick_spacing):
    return tick_spacing * round(tick / tick_spacing)

def floor_tick(tick, tick_spacing):
    return tick - (tick % tick_spacing)

def ceil_tick(tick, tick_spacing):
    return tick + (tick_spacing - (tick % tick_spacing)) if tick % tick_spacing != 0 else tick

def get_amounts_from_liquidity(L, price, tickLower, tickUpper):
    sqrtP = math.sqrt(price)
    sqrtPLow = math.sqrt(tick_to_price(tickLower))
    sqrtPHigh = math.sqrt(tick_to_price(tickUpper))

    if sqrtP <= sqrtPLow:
        # Apenas em token 0
        amount0 = L * (sqrtPHigh - sqrtPLow) / (sqrtPLow * sqrtPHigh)
        amount1 = 0
        status = "below_range"

    elif sqrtP >= sqrtPHigh:
        # Totalmente em token 1
        amount0 = 0
        amount1 = L * (sqrtPHigh - sqrtPLow)
        status = "above_range"

    else: 
        # Dentro da faixa de preço
        amount0 = L * (sqrtPHigh - sqrtP) / (sqrtP * sqrtPHigh)
        amount1 = L * (sqrtP - sqrtPLow)
        status = "in_range"
    
    return max(amount0, 0), max(amount1, 0), status

def get_position_value_usd(amount0, amount1, price):
    # valor da posição em USD no momento do tempo
    # considerando usdc = 1 usd
    return amount0 * price + amount1

def simulate_il_range(
        value_usd,
        price_initial,
        tickLower,
        tickUpper,
        price_min,
        price_max,
        steps=100,
        output_dir= "simulations",
        output_filename= "simulations.csv"
):
    
    sqrtP_initial = math.sqrt(price_initial)
    sqrtPLow = math.sqrt(tick_to_price(tickLower))
    sqrtPHigh = math.sqrt(tick_to_price(tickUpper))

    #Liquidez e tokens iniciais na criação da posição
    L, amount0_init, amount1_init, _, _ = get_L_and_amounts(
        value_usd, price_initial, sqrtP_initial, sqrtPLow, sqrtPHigh
    )

    rows = []
    for i in range(steps + 1):
        price_t = price_min + i * (price_max - price_min) / steps

        amount0_t, amount1_t, status = get_amounts_from_liquidity(L, price_t, tickLower, tickUpper)
        value_lp = get_position_value_usd(amount0_t, amount1_t, price_t)
        value_hodl = amount0_init * price_t + amount1_init
        il = (value_lp - value_hodl) / value_hodl if value_hodl != 0 else 0
        il_absolute = value_lp - value_hodl
        if fee_percent > 0:
            volume_necessario = abs(il_absolute) / fee_percent
            volume_diario = volume_necessario / days_target
            apr = (volume_diario * fee_percent * 365) / value_lp if value_lp != 0 else 0
        else:
            volume_necessario = 0
            volume_diario = 0
            apr = 0

        rows.append({
            "price": price_t,
            "amount0": amount0_t,
            "amount1": amount1_t,
            "value_lp": value_lp,
            "value_hodl": value_hodl,
            "impermanent_loss": il,
            "Absolute impermanent loss value": il_absolute,
            "range_status": status,
            "expected_volum_usd": volume_necessario,
            "daily_volum_usd": volume_diario,
            "APR": apr
        })

    # Criar diretório se não existir
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_filename)

    

    # Salvar CSV
    with open(output_path, mode="w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ Simulação salva em: {output_path}")
    return rows

value_usd = 143635

# sqrtPriceX96 = 17474757313379528450999647145
# price = sqrtX96_to_price(sqrtPriceX96)
tickLower = price_to_tick(0.0560870533943866)
tickUpper = price_to_tick(0.0610167550777861)
use_manual_sqrtPrice = False        # True para usar o sqrtPrice manualmente
manual_sqrtPriceX96 = 17474757313379528450999647145
price_column = "price_vwap"
date_column = "date"            # Mudar para timestamp se quiser passar por timestamp
start_key = "2023-06-28"
end_key = "2023-07-28"
# currentTick = price_to_tick(price)
tick = -30233
tick_spacing = 60
position_low = tick_to_price(-32880)
position_high = tick_to_price(-15300)

if modo == "simulacao":
    price_initial = 0.053        # Valor para simulaçao
    fee_percent = 0.0025        # para taxa da pool em 0.25%
    days_target = 30              # tempo para cobrir o IL em dias
    sim_rows = simulate_il_range(    
        value_usd=143635,
        price_initial=price_initial,
        tickLower=tickLower,
        tickUpper=tickUpper,
        price_min=0.05081391162226479,
        price_max=0.05528013707901989,
        steps=200
    )

# price_current = price
actual_tick_price = tick_to_price(tick)
# sqrtP = math.sqrt(price_current)
sqrtPLow = math.sqrt(tick_to_price(tickLower))
sqrtPHigh = math.sqrt(tick_to_price(tickUpper))

if modo == "historico":
    df = pd.read_csv("mxn_expected_range_with_vol.csv")

    # Selecionar linha inicial e final por chave
    start_matches = df[df[date_column].astype(str) == str(start_key)]
    end_matches = df[df[date_column].astype(str) == str(end_key)]

    if start_matches.empty or end_matches.empty:
        print("❌ Data de início ou fim não encontrada no CSV!")
        print(f"Datas disponíveis no campo '{date_column}':")
        print(df[date_column].dropna().astype(str).unique()[:10])  # Mostra amostra
        exit(1)

    start_row = start_matches.iloc[0]
    end_row = end_matches.iloc[0]

    # === Escolha do preço inicial ===
    if use_manual_sqrtPrice:
        initial_price = sqrtX96_to_price(manual_sqrtPriceX96)
    else:
        initial_price = start_row[price_column]

    # === Calcular liquidez inicial ===
    sqrtP = math.sqrt(initial_price)
    sqrtPLow = math.sqrt(tick_to_price(tickLower))
    sqrtPHigh = math.sqrt(tick_to_price(tickUpper))
    L, amount0_init, amount1_init, term0_init, term1_init = get_L_and_amounts(value_usd, initial_price, sqrtP, sqrtPLow, sqrtPHigh)

    # L, amount0, amount1, term0, term1 = get_L_and_amounts(value_usd, price, sqrtP, sqrtPLow, sqrtPHigh)


    # === Aplicar rebalancing ao intervalo ===
    df_interval = df[(df[date_column] >= str(start_key)) & (df[date_column] <= str(end_key))].copy()

    results = []
    for _, row in df_interval.iterrows():
        price_t = row[price_column]
        amount0, amount1, status = get_amounts_from_liquidity(L, price_t, tickLower, tickUpper)
        value_usd_t = get_position_value_usd(amount0, amount1, price_t)

        value_hodl = amount0_init * price_t + amount1_init

        il = (value_usd_t - value_hodl) / value_hodl if value_hodl != 0 else 0
        il_absolute = value_usd_t - value_hodl

        results.append({
            "timestamp": row["timestamp"],
            "date": row["date"],
            "price": price_t,
            "amount0": amount0,
            "amount1": amount1,
            "value_usd": value_usd_t,
            "status_range": status,
            "value_hodl": value_hodl,
            "impermanent_loss": il,
            "Absolute impermanent loss value": il_absolute
        })

    # print(f"Current Price: {price}")
    print(f"Tick Lower: {tickLower}")
    print(f"Tick Upper: {tickUpper}")
    # print(f"Current Tick: {currentTick}")
    print(f"Liquidity L: {L:.2f}")
    print(f"Amount0 (MXN): {amount0:.6f}")
    print(f"Amount1 (USDC): {amount1:.6f}")

    print(f"Mais próximo: {nearest_valid_tick(tick, tick_spacing)}") 
    print(f"Floor: {floor_tick(tick, tick_spacing)}")                 
    print(f"Ceil: {ceil_tick(tick, tick_spacing)}") 

    print(f"SqrtPrice atual: {sqrtP}")
    print(f"SqrtPrice lower: {sqrtPLow}")
    print(f"SqrtPrice upper: {sqrtPHigh}")
    print(f"Está dentro da faixa? {sqrtPLow < sqrtP < sqrtPHigh}")
    # print(f"Primeiro termo: {term0}")
    # print(f"Segundo termo: {term1}")
    # print(f"Calculando: {term0 * price + term1}")

    print(f"Preço da faixa inferior: {position_low}")
    print(f"Preço da faixa superior: {position_high}")
    print(f"Preço referente ao tick {tick}: {actual_tick_price}")

    # === Exportar CSV ===
    output_dir = "rebalancing"
    os.makedirs(output_dir, exist_ok=True)
    output_path = f"{output_dir}/rebalancing_{start_key}_to_{end_key}.csv"

    pd.DataFrame(results).to_csv(output_path, index=False)
    print(f"✅ Rebalancing salvo em: {output_path}")
