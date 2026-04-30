from polygon import RESTClient
import os
from dotenv import load_dotenv
load_dotenv(override=True)

API_KEY_POLYGON_IO = os.getenv('API_KEY_POLYGON_IO')
client = RESTClient(API_KEY_POLYGON_IO)

class PolygonIo:
    @classmethod
    def get_ticker_detail(cls, ticker):
        return client.get_ticker_details(ticker)

    @classmethod
    def get_prices_between_dates(cls, ticker, timespan, start_timestamp, end_timestamp, limit=5000):
        aggs = []
        for a in client.list_aggs(
            ticker,
            1,
            timespan,
            start_timestamp,
            end_timestamp,
            adjusted="true",
            sort="asc",
            limit=limit,
        ):
            
            if a.timestamp >= int(start_timestamp) and a.timestamp <= int(end_timestamp):
                aggs.append( {
                    "price": a.open,
                    "timestamp": int(a.timestamp / 1000)
                })

        return aggs
    

    @classmethod
    def get_daily_prices_between_dates(cls, ticker, start_timestamp, end_timestamp, limit=5000):
        aggs = []
        for a in client.list_aggs(
            ticker,
            1,
            'day',
            start_timestamp,
            end_timestamp,
            adjusted="true",
            sort="asc",
            limit=limit,
        ):
            
            aggs.append( {
                "price_open": a.open,
                "price_hight": a.high,
                "price_low": a.low,
                "price_vwap": a.vwap,
                "timestamp": int(a.timestamp / 1000)
                })

        return aggs
