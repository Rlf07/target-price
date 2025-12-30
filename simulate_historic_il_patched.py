
import pandas as pd
import math
import os
import re
import glob

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

def _select_range_columns(csv_path, df_columns):
    """
    Rule:
      - If the file name DOES NOT contain 'shifted50', use price_min_shifted / price_max_shifted
      - Otherwise (it is a shifted50 file), use price_min_expected / price_max_expected
    """
    fname = os.path.basename(csv_path).lower()
    use_shifted = 'shifted50' not in fname
    min_col = 'price_min_shifted' if use_shifted else 'price_min_expected'
    max_col = 'price_max_shifted' if use_shifted else 'price_max_expected'

    # Sanity check to avoid silent KeyError later
    for col in (min_col, max_col, 'price_open'):
        if col not in df_columns:
            raise KeyError(f"Column '{col}' not found in CSV. Available: {list(df_columns)}")
    return min_col, max_col, use_shifted

def simulate_historic_il(
    csv_path,
    output_path,
    value_usd=1000,
    fee_percent=0.0025,
    start_date=None,
    end_date=None,
    rebalance_period_days=1  # define o intervalo de rebalanceamento
):
    # Load
    df = pd.read_csv(csv_path)

    # Decide which range columns to use
    min_col, max_col, use_shifted = _select_range_columns(csv_path, df.columns)

    # Clean & filter
    df = df.dropna(subset=['price_open', min_col, max_col])
    df['date'] = pd.to_datetime(df['date'])

    if start_date:
        df = df[df['date'] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df['date'] <= pd.to_datetime(end_date)]
    df = df.reset_index(drop=True)

    results = []
    cumulative_il = 0
    cumulative_rebalance_cost = 0

    last_range = None
    last_L = None
    last_rebalance_date = None
    last_amount0 = None
    last_amount1 = None

    for i in range(len(df) - 1):
        row_start = df.iloc[i]
        row_end = df.iloc[i + 1]

        price_start = row_start['price_open']
        price_end = row_end['price_open']
        current_date = row_start['date']

        # Rebalance if first step or period elapsed
        if i == 0 or (current_date - last_rebalance_date).days >= rebalance_period_days:
            range_start = (row_start[min_col], row_start[max_col])
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
            "range_end_min": row_end[min_col],
            "range_end_max": row_end[max_col],
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

    # Construir automaticamente o caminho de saída a partir do nome do arquivo de entrada
    def build_output_path(csv_path, rebalance_period_days, use_shifted):
        fname = os.path.basename(csv_path)
        m = re.match(r"(?P<token>[a-zA-Z0-9]+)_expected_range_with_vol(?P<conf>\d+)_shifted(?P<perc>\d+)\.csv", fname)
        if not m:
            raise ValueError(f"Nome de arquivo inesperado: {fname}")

        token = m.group("token")
        conf = m.group("conf")
        perc = m.group("perc")

        base_dir = f"simulations/historic_simulation_il/{token}_days_rebalancing/confidence{conf}{perc}"
        os.makedirs(base_dir, exist_ok=True)

        range_tag = "using_shifted" if use_shifted else "using_expected"
        output_file = f"shifted_rebalance{rebalance_period_days}d{conf}{perc}_{range_tag}.csv"
        return os.path.join(base_dir, output_file)

    output_path = build_output_path(csv_path, rebalance_period_days, use_shifted)
    results_df.to_csv(output_path, index=False)
    print(f"✅ Resultado salvo em: {output_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, required=True,
                        help="Arquivo CSV único OU pasta (ex: expected_ranges/eur)")
    parser.add_argument("--value_usd", type=float, default=260000)
    parser.add_argument("--fee_percent", type=float, default=0.0005)
    parser.add_argument("--start_date", type=str, default="2023-09-24")
    parser.add_argument("--end_date", type=str, default="2025-09-22")
    parser.add_argument("--max_days", type=int, default=7)
    args = parser.parse_args()

    # Se input for pasta → pega todos CSVs, senão só 1 arquivo
    if os.path.isdir(args.input):
        files = glob.glob(os.path.join(args.input, "*.csv"))
    else:
        files = [args.input]

    for csv_file in files:
        for days in range(1, args.max_days + 1):
            simulate_historic_il(
                csv_path=csv_file,
                output_path="IGNORED.csv",  # substituído dentro da função
                value_usd=args.value_usd,
                fee_percent=args.fee_percent,
                start_date=args.start_date,
                end_date=args.end_date,
                rebalance_period_days=days
            )

