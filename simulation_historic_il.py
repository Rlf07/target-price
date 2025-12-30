import pandas as pd
import math
import os

def tick_to_price(tick):
    return 1.0001 ** tick

def price_to_tick(price):
    return int(math.log(price) / math.log(1.0001))

def price_to_sqrt(price):
    return math.sqrt(price)

def get_liquidity(value_usd, price, sqrtP, sqrtPLow, sqrtPHigh):
    if not (sqrtPLow < sqrtP < sqrtPHigh):
        if sqrtP <= sqrtPLow:
            amount0 = value_usd / price
            amount1 = 0
        else:
            amount0 = 0
            amount1 = value_usd
        return 0, amount0, amount1

    term0 = (sqrtPHigh - sqrtP) / (sqrtP * sqrtPHigh)
    term1 = sqrtP - sqrtPLow

    L = value_usd / (term0 * price + term1)
    amount0 = L * term0
    amount1 = L * term1

    return L, amount0, amount1

def get_amounts_from_liquidity(L, price, sqrtPLow, sqrtPHigh):
    sqrtP = math.sqrt(price)

    if sqrtP <= sqrtPLow:
        amount0 = L * (sqrtPHigh - sqrtPLow) / (sqrtPLow * sqrtPHigh)
        amount1 = 0
    elif sqrtP >= sqrtPHigh:
        amount0 = 0
        amount1 = L * (sqrtPHigh - sqrtPLow)
    else:
        amount0 = L * (sqrtPHigh - sqrtP) / (sqrtP * sqrtPHigh)
        amount1 = L * (sqrtP - sqrtPLow)

    return max(amount0, 0), max(amount1, 0)

def simulate_historic_il(
    csv_path,
    output_path,
    value_usd=1000,
    fee_percent=0.0025,
    start_date=None,
    end_date=None,
    rebalance_period_days=1  # NOVO: define o intervalo de rebalanceamento
):
    df = pd.read_csv(csv_path)
    df = df.dropna(subset=['price_vwap', 'price_min_expected', 'price_max_expected'])
    df['date'] = pd.to_datetime(df['date'])

    if start_date:
        df = df[df['date'] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df['date'] <= pd.to_datetime(end_date)]

    df = df.reset_index(drop=True)

    results = []
    cumulative_il = 0
    cumulative_rebalance_cost = 0

    last_rebalance_index = 0
    last_range = None
    last_L = None
    last_rebalance_date = None

    for i in range(len(df) - 1):
        row_start = df.iloc[i]
        row_end = df.iloc[i + 1]

        price_start = row_start['price_vwap']
        price_end = row_end['price_vwap']
        current_date = row_start['date']

        # Se for o primeiro rebalance ou passou o período, fazemos novo rebalance
        if i == 0 or (current_date - last_rebalance_date).days >= rebalance_period_days:
            range_start = (row_start['price_min_expected'], row_start['price_max_expected'])
            sqrtP_start = price_to_sqrt(price_start)
            sqrtPLow_start = price_to_sqrt(range_start[0])
            sqrtPHigh_start = price_to_sqrt(range_start[1])

            L, amount0_start, amount1_start = get_liquidity(
                value_usd, price_start, sqrtP_start, sqrtPLow_start, sqrtPHigh_start
            )

            last_range = range_start
            last_L = L
            last_amount0 = amount0_start
            last_amount1 = amount1_start
            last_rebalance_date = current_date
        else:
            range_start = last_range
            L = last_L
            amount0_start = last_amount0
            amount1_start = last_amount1

        sqrtPLow_start = price_to_sqrt(range_start[0])
        sqrtPHigh_start = price_to_sqrt(range_start[1])
        value_start = amount0_start * price_start + amount1_start
        value_hold = amount0_start * price_end + amount1_start

        amount0_end, amount1_end = get_amounts_from_liquidity(
            L, price_end, sqrtPLow_start, sqrtPHigh_start
        )
        value_end = amount0_end * price_end + amount1_end

        il = (value_end - value_hold) / value_hold if value_hold != 0 else 0
        il_value = value_end - value_hold

        token0_value_start = amount0_start * price_end
        token1_value_start = amount1_start
        total_value = token0_value_start + token1_value_start

        ratio0 = token0_value_start / total_value if total_value else 0
        ratio1 = token1_value_start / total_value if total_value else 0
        ideal_ratio0 = (amount0_end * price_end) / value_end if value_end else 0
        ideal_ratio1 = amount1_end / value_end if value_end else 0

        delta0_value = abs(ratio0 - ideal_ratio0) * total_value
        delta1_value = abs(ratio1 - ideal_ratio1) * total_value

        rebalance_cost = fee_percent * (delta0_value + delta1_value) / 2
        net_value_after_cost = value_end - rebalance_cost
        il_net = (net_value_after_cost - value_hold) / value_hold if value_hold != 0 else 0

        cumulative_il += il_value
        cumulative_rebalance_cost += rebalance_cost
        cumulative_il_net = cumulative_il - cumulative_rebalance_cost

        day_volum_expected = abs(il_value + rebalance_cost) / fee_percent if fee_percent > 0 else 0
        cumulative_volum = abs(cumulative_il_net) / fee_percent if fee_percent > 0 else 0
        min_apr_required = (day_volum_expected * fee_percent * 365) / value_end if value_end != 0 else 0

        results.append({
            "date_start": row_start['date'],
            "date_end": row_end['date'],
            "price_start": price_start,
            "price_end": price_end,
            "range_start_min": range_start[0],
            "range_start_max": range_start[1],
            "range_end_min": row_end['price_min_expected'],
            "range_end_max": row_end['price_max_expected'],
            "amount0_start": amount0_start,
            "amount1_start": amount1_start,
            "amount0_end": amount0_end,
            "amount1_end": amount1_end,
            "value_start": value_start,
            "value_hold": value_hold,
            "value_end": value_end,
            "il": il,
            "il_value": il_value,
            "il_net": il_net,
            "rebalance_cost": rebalance_cost,
            "net_value_after_cost": net_value_after_cost,
            "day_volum_expected": day_volum_expected,
            "cumulative_il": cumulative_il,
            "cumulative_rebalance_cost": cumulative_rebalance_cost,
            "cumulative_il_net": cumulative_il_net,
            "cumulative_volum": cumulative_volum,
            "min_apr_required": min_apr_required
        })

    results_df = pd.DataFrame(results)

    base, ext = os.path.splitext(output_path)
    output_path = f"{base}/eur_days_rebalancing/confidence9930/shifted_rebalance{rebalance_period_days}d9930{ext}"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    results_df.to_csv(output_path, index=False)
    print(f"✅ Resultado salvo em: {output_path}")


if __name__ == "__main__":
    # Parâmetros comuns
    csv_file = "expected_ranges/eur/eur_expected_range_with_vol99_shifted30.csv"
    base_output = "simulations/historic_simulation_il.csv"

    for days in range(1, 8):  # Loop de 1 até 7
        simulate_historic_il(
            csv_path=csv_file,
            output_path=base_output,  # A função já monta o nome final
            value_usd=100000,
            fee_percent=0.0005,  # 0.05%
            start_date="2023-08-13",
            end_date="2025-08-12",
            rebalance_period_days=days
        )

