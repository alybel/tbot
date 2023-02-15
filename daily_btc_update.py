import time

import matplotlib.pyplot as plt
import requests
import pandas as pd
import datetime
import functools
import ta
import openai
import seaborn as sns

sns.set_theme()


def try_repeated(n, sleep):
    def repeated(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            r = None
            count = 0
            while count < n:
                try:
                    r = func(*args, **kwargs)
                    if r is not None:
                        break
                    if r is None:
                        raise Exception('None was returned')
                except Exception as e:
                    if count == n - 1:
                        raise e
                    else:
                        time.sleep(sleep)
                count += 1
            return r

        return wrapper

    return repeated


@try_repeated(3, 5)
def ask_openai(prompt):
    print(prompt)
    key = open('openai_key', 'r').read()
    openai.api_key = key

    #    prompt = "write a fascinated tweet on a newly tested ai service for bitcoin price discovery"

    response = openai.Completion.create(
        model="text-davinci-003",
        prompt=prompt,
        temperature=0.2,
        max_tokens=200
    )
    answer_text = response.choices[0]['text']
    if "we" in answer_text:
        return None
    return answer_text


@try_repeated(5, 2)
def get_binance_orderbook_ticker(ticker):
    url = f'https://www.binance.com/api/v3/ticker/bookTicker?symbol={ticker}'
    d = requests.get(url).json()
    d['bidPrice'] = float(d['bidPrice'])
    d['askPrice'] = float(d['askPrice'])
    d['bidQty'] = float(d['bidQty'])
    d['askQty'] = float(d['askQty'])
    return d


@try_repeated(5, 2)
def get_binance_data_request_(ticker, interval='4h', limit=1000, start_time=None, end_time=None):
    """
    https://stackoverflow.com/questions/51358147/fetch-candlestick-kline-data-from-binance-api-using-python-preferably-requests
    interval: str tick interval - 4h/1h/1d ...
    """
    columns = ['open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades',
               'taker_base_vol', 'taker_quote_vol', 'ignore']
    if start_time is None and end_time is None:
        url = f'https://www.binance.com/api/v3/klines?symbol={ticker}&interval={interval}&limit={limit}'
    else:
        start_time = int(datetime.datetime.timestamp(pd.to_datetime(start_time)) * 1000)
        if end_time is None:
            end_time = int(datetime.datetime.timestamp(pd.Timestamp.today()) * 1000)
        url = f'https://www.binance.com/api/v3/klines?symbol={ticker}&interval={interval}&limit={limit}&startTime={start_time}&endTime={end_time}'
        print(url)
    data = pd.DataFrame(requests.get(url).json(), columns=columns, dtype=float)
    data.index = [pd.to_datetime(x, unit='ms').strftime('%Y-%m-%d %H:%M:%S') for x in data.open_time]
    usecols = ['open', 'high', 'low', 'close', 'volume', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol']
    data = data[usecols]
    data.index = pd.to_datetime(data.index)
    return data


def get_daily_image():
    df = get_binance_data_request_(ticker='BTCUSDT', interval='1h', limit=24 * 2)
    went_up = (df['close'].iloc[-1] - df['close'].iloc[-24]) > 0
    ax = df['close'].plot(figsize=(12, 6))

    ax = df['close'][-24:].plot(ax=ax, color='green' if went_up else 'red', lw=2)
    fig = ax.get_figure()
    plt.title('48h Bitcoin Price Development', fontdict={'size': 20})
    plt.ylabel('Price [USD]')
    plt.xlabel('Date')
    fig.savefig('plot.png')


def get_daily_update():
    df = get_binance_data_request_(ticker='BTCUSDT', interval='1h', limit=24 * 2)
    ta_all_indicators_df = ta.add_all_ta_features(df.copy(), open="open", high="high",
                                                  low="low", close="close",
                                                  volume="volume")

    last_values = ta_all_indicators_df.iloc[-1]

    indicators = {
        'CCI': last_values['trend_cci'],
        'MACD': last_values['trend_macd_signal'],
        '10d_Momentum': 100 * (
                ta_all_indicators_df.iloc[-10]['close'] / ta_all_indicators_df.iloc[-1]['close'] - 1),
        '30d_Momentum': 100 * (
                ta_all_indicators_df.iloc[-48]['close'] / ta_all_indicators_df.iloc[-1]['close'] - 1),
        'ATR': last_values['volatility_atr'],
        'RSI': last_values['momentum_rsi'],
        'WR': last_values['momentum_wr']
    }
    day_return = 100 * (df['close'].iloc[-1] / df['close'].iloc[-24] - 1)
    df_ind = pd.DataFrame([indicators])
    df_ind.index.name = 'metric value'

    prompt = (
            'produce a price movement forecast for %s based on the following intraday technical indicators, which are produced on the last 24 hours intraday data:  '
            ' MACD: %1.2f '
            ' CCI: %1.2f '
            ' 10 hours Momentum: %1.2f Percent '
            ' 30 hours Momentum: %1.2f Percent '
            ' ATR: %1.2f '
            ' RSI: %1.2f '
            ' WR: %1.2f '
            '24 hours return: %1.2f Percent'
            % ('Bitcoin', indicators['MACD'], indicators['CCI'], indicators['10d_Momentum'],
               indicators['30d_Momentum'], indicators['ATR'], indicators['RSI'], indicators['WR'],
               day_return))
    print(prompt)
    result = ask_openai(prompt)
    return result
