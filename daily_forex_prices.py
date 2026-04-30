from src.polygonio import PolygonIo
import time
import json
from pathlib import Path
from datetime import datetime

coin = 'gbp'
current_timestamp = int(time.time())
seconds_in_a_year = 2 * 365 * 24 * 60 * 60
one_year_ago = current_timestamp - seconds_in_a_year
ticker = f'C:{coin.upper()}USD'
result = PolygonIo.get_daily_prices_between_dates(ticker, one_year_ago, current_timestamp)

output_dir = Path(__file__).resolve().parent / "json" / f"forex-{coin}"
output_dir.mkdir(parents=True, exist_ok=True)
output_path = output_dir / f"{coin}_daily_prices.json"

with open(output_path, 'w', encoding="utf-8") as file:
    json.dump(result, file, indent=4)

with open(output_path, "r", encoding="utf-8") as f:
    data = json.load(f)

for item in data:
    ts = item.get("timestamp")
    if ts is not None:
        dt = datetime.utcfromtimestamp(ts)
        item["date"] = dt.strftime("%Y-%m-%d %H:%M:%S")

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=4)
print(f"JSON salvo em: {output_path}")

