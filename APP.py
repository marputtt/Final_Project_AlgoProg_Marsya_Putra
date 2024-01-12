import websocket
import config
import json
import talib
import time
import datetime
import sys
import re
import os
import pandas as pd
from binance.client import Client
from binance.enums import *
from binance.exceptions import BinanceAPIException, BinanceOrderException

class CryptoBot:
    def __init__(self, symbol, tframe, leverage, rrr, risk_percent, risk_usd, stop_csticks, stop_range, slowest_EMA, macd_fast, macd_slow, macd_signal, atr_period):
        self.symbol = symbol                          # trading symbol
        self.tframe = tframe                          # time frame
        self.leverage = leverage                      # leverage multiplier
        self.rrr = rrr                                # risk-reward ratio
        self.risk_percent = risk_percent              # risk percentage
        self.risk_usd = risk_usd                      # risk amount in USD
        self.stop_csticks = stop_csticks              # stop candle count
        self.stop_range = stop_range                  # stop price range
        self.slowest_EMA = slowest_EMA                # slowest exponential moving average
        self.macd_fast = macd_fast                    # MACD fast moving average
        self.macd_slow = macd_slow                    # MACD slow moving average
        self.macd_signal = macd_signal                # MACD signal line
        self.atr_period = atr_period                  # Average True Range period

        self.futures_websocket = f'wss://stream.binancefuture.com/ws/{self.symbol}@kline_{self.tframe}'
        self.client = Client(config.API_KEY, config.API_SECRET,  testnet=True)
        self.TRADE_SYMBOL = self.symbol.upper()
        self.df_final = None
        self.round_off = None

    def initialize(self):
        if self.tframe[-1] == 'm':
            tf1 = int(re.findall('\d+', self.tframe)[0])
            self.tme_frame = 1 * tf1
        elif self.tframe[-1] == 'h':
            tf1 = int(re.findall('\d+', self.tframe)[0])
            self.tme_frame = 60 * tf1

         
        self.futures_websocket = f'wss://stream.binancefuture.com/ws/{self.symbol}@kline_{self.tframe}'

        symbols = self.client.futures_position_information()
        df = pd.DataFrame(symbols)
        symbol_loc = df.index[df.symbol == self.TRADE_SYMBOL]
        self.SYMBOL_POS = symbol_loc[-1]

        data = self.client.futures_exchange_info()

        symbol_list = []
        precision = []

        for pair in data['symbols']:
            if pair['status'] == 'TRADING':
                symbol_list.append(pair['symbol'])
                precision.append(pair['pricePrecision'])

        df2 = pd.DataFrame(symbol_list)
        df1 = pd.DataFrame(precision)
        merge = pd.concat([df1, df2], axis=1)
        merge.columns = ['precision', 'symbol']
        merge.set_index('precision', inplace=True)
        symbol_loc = merge.index[merge.symbol == self.TRADE_SYMBOL]
        self.round_off = symbol_loc[-1]

        start_balance = self.client.futures_account_balance()
        initial_balance = start_balance[3]['balance']
        print("================================")
        print('Initial balance:  {}'.format(initial_balance))
        print("================================")
        with open("initial_balance.txt", "r+") as file_object:
            file_object.seek(0)
            data = file_object.read(100)
            if len(data) > 0:
                file_object.write("\n")
            file_object.write(initial_balance)

        time.sleep(1)

        change_leverage = self.client.futures_change_leverage(symbol=self.TRADE_SYMBOL, leverage=self.leverage)
        print('Leverage set to: ', change_leverage['leverage'])

        time.sleep(1)

        csticks = self.client.futures_klines(symbol=self.TRADE_SYMBOL, interval=self.tframe)
        df = pd.DataFrame(csticks)
        df_edited = df.drop([0, 6, 7, 8, 9, 10, 11], axis=1)
        df_final = df_edited.drop(df_edited.tail(1).index)
        df_final.columns = ['o', 'h', 'l', 'c', 'v']
        df_final['slowest_EMA'] = round(talib.EMA(df_final['c'], self.slowest_EMA), self.round_off)
        df_final['macd'], df_final['macdSignal'], df_final['macdHist'] = talib.MACD(df_final['c'], fastperiod=self.macd_fast, slowperiod=self.macd_slow, signalperiod=self.macd_signal)
        df_final['hlc_ave'] = (df_final['h'].astype(float) + df_final['l'].astype(float) + df_final['c'].astype(float)) / 3
        df_final['VWAP'] = (df_final['hlc_ave'] * df_final['v'].astype(float)).cumsum() / df_final['v'].astype(float).cumsum()
        df_final['ATR'] = talib.ATR(df_final['h'], df_final['l'], df_final['c'], timeperiod=self.atr_period)
        self.df_final = df_final
        print(self.df_final)

        
        # For testing purposes, place a test buy order as soon as the bot starts
        test_buy_price = float(self.df_final['c'].tail(1).iloc[0])  # Use the last closing price as the test buy price
        test_buy_price = round(test_buy_price, self.round_off)  # Round to the appropriate precision
        test_quantity = 0.003  # Adjust the quantity for testing purposes

        try:
            test_buy_order = self.client.futures_create_order(
                symbol=self.TRADE_SYMBOL, side='BUY', type='MARKET',
                quantity=test_quantity
            )
            print('Test Buy Order Placed Successfully:', test_buy_order)

            # Set Take Profit and Stop Loss for the test position
            test_position_amt = float(test_buy_order['executedQty'])
            test_take_profit = round(test_buy_price * 1.01, self.round_off)  # 1% above the test buy price
            test_stop_loss = round(test_buy_price * 0.99, self.round_off)  # 1% below the test buy price

            # Place Take Profit and Stop Loss orders
            test_tp_order = self.client.futures_create_order(
                symbol=self.TRADE_SYMBOL, side='SELL', type='TAKE_PROFIT_MARKET',
                stopPrice=test_take_profit, closePosition=True, quantity=test_position_amt
            )
            test_sl_order = self.client.futures_create_order(
                symbol=self.TRADE_SYMBOL, side='SELL', type='STOP_MARKET',
                stopPrice=test_stop_loss, closePosition=True, quantity=test_position_amt
            )

            print('Take Profit Order Placed Successfully:', test_tp_order)
            print('Stop Loss Order Placed Successfully:', test_sl_order)

        except BinanceAPIException as e:
            # Handle API exceptions
            print(f"Error placing test buy order: {e}")
        except BinanceOrderException as e:
            # Handle order exceptions
            print(f"Error placing test buy order: {e}")



        
    def run_bot(self):
        try:
            ws = websocket.WebSocketApp(self.futures_websocket, on_open=self.on_open, on_close=self.on_close, on_message=self.on_message)
            ws.run_forever()

        except KeyboardInterrupt:
            self.stop_bot()

        except Exception as e:
            print(f"An error occurred: {e}")
            self.stop_bot()
    
    def stop_bot(self):
        print("Stopping the bot.")
        sys.exit()

    
    def on_open(self, ws):
        print('Please waait until the right momentum')
        print('WebSocket connection opened successfully.')
        

    def on_close(self, ws):
        print('Connection Closed')

    def on_message(self, ws, message):
        
        json_message = json.loads(message)
        candle = json_message['k']
        candle_closed = candle['x']
       # print('ITS WORKING!!!!!!!')

        
        
        if candle_closed:
            open_data = candle['o']
            high_data = candle['h']
            low_data = candle['l']
            close_data = candle['c']
            self.df_final = self.df_final.append(candle, ignore_index=True)
            self.df_final['slowest_EMA'] = round(talib.EMA(self.df_final['c'], self.slowest_EMA), self.round_off)
            self.df_final['macd'], self.df_final['macdSignal'], self.df_final['macdHist'] = talib.MACD(
                self.df_final['c'], fastperiod=self.macd_fast, slowperiod=self.macd_slow, signalperiod=self.macd_signal)
            self.df_final['hlc_ave'] = (self.df_final['h'].astype(float) + self.df_final['l'].astype(float) + self.df_final['c'].astype(float)) / 3
            self.df_final['VWAP'] = (
                    self.df_final['hlc_ave'] * self.df_final['v'].astype(float)).cumsum() / self.df_final['v'].astype(float).cumsum()
            self.df_final['ATR'] = talib.ATR(self.df_final['h'], self.df_final['l'], self.df_final['c'],
                                        timeperiod=self.atr_period)

            last_open = self.df_final['o'].tail(1)
            last_high = self.df_final['h'].tail(1)
            last_low = self.df_final['l'].tail(1)
            last_close = self.df_final['c'].tail(1)
            last_slowest_EMA = self.df_final['slowest_EMA'].tail(1)
            last_macd = round(self.df_final['macd'].tail(1), self.round_off + 1)
            last_macdSignal = round(self.df_final['macdSignal'].tail(1), self.round_off + 1)
            last_VWAP = round(self.df_final['VWAP'].tail(1), self.round_off + 1)
            last_ATR = round(self.df_final['ATR'].tail(1), self.round_off)
            macd_3c_ago = round(self.df_final['macd'].iloc[-3], self.round_off + 1)
            macdSignal_3c_ago = round(self.df_final['macdSignal'].iloc[-3], self.round_off + 1)
            macd_2c_ago = round(self.df_final['macd'].iloc[-2], self.round_off + 1)

            print('==================================================================')
            now = datetime.datetime.now()
            print('Current time is: {}'.format(now.strftime("%d/%m/%Y %H:%M:%S")))
            print('==================================================================')

            print("Open: {}".format(open_data), "  |  " "High: {}".format(high_data), "  |  " "Low: {}".format(low_data),
                "  |  " "Close: {}".format(close_data))
            print('Slowest EMA: {}'.format(float(self.df_final['slowest_EMA'].tail(1))))
            print('MACD: {:f}'.format(float(last_macd)))
            print('MACD Signal: {:f}'.format(float(last_macdSignal)))
            print('VWAP: {:f}'.format(float(last_VWAP)))
            print('ATR: {}'.format(float(last_ATR)))

            check_symbol_loc = self.client.futures_position_information()
            df = pd.DataFrame(check_symbol_loc)
            position_amount = df.loc[self.SYMBOL_POS, 'positionAmt']
            symbol_loc = df.loc[self.SYMBOL_POS, 'symbol']

            # trade symbol and location in dataframe checker
            if symbol_loc != self.TRADE_SYMBOL:
                os.startfile(__file__)
                sys.exit('Warning: Symbol Position and Trade Symbol do not match, bot is restarting..')

            # cancels all open orders
            if float(position_amount) == 0:
                cancel_open_orders = self.client.futures_cancel_all_open_orders(symbol=self.TRADE_SYMBOL)

                time.sleep(1)

            highest = max(self.df_final['h'].tail(self.stop_csticks))
            lowest = min(self.df_final['l'].tail(self.stop_csticks))
            SL_range_buy = ((float(last_low) / float(lowest)) - 1) * 100
            SL_range_sell = ((float(highest) / float(last_high)) - 1) * 100

            # Buy Condition
            if float(macd_3c_ago) < float(macdSignal_3c_ago) and float(last_macd) > float(last_macdSignal) and float(
                    macd_2c_ago) < 0 and float(last_close) > float(last_slowest_EMA) and float(
                last_close) > float(last_VWAP) and SL_range_buy <= self.stop_range:

                # condition 1: check if the current balance is still above your risk
                now_balance = self.client.futures_account_balance()
                current_balance = now_balance[0]['balance']
                with open("current_balance.txt", "a+") as file_object:
                    file_object.seek(0)
                    data = file_object.read(100)
                    if len(data) > 0:
                        file_object.write("\n")
                    file_object.write(current_balance)
                with open('initial_balance.txt', 'r') as f:
                    lines = f.read().splitlines()
                    initial = float(lines[-1])
                with open('current_balance.txt', 'r') as f:
                    lines = f.read().splitlines()
                    current = float(lines[-1])

                    if (initial - (initial * self.risk_percent)) > current:
                        time.sleep(2)
                        sys.exit('Today is not your day. Bot is terminating.')

                time.sleep(1)

                # condition 2: check if in position to avoid buying when already in position
                check_if_in_position = self.client.futures_position_information()
                df = pd.DataFrame(check_if_in_position)
                position_amount = df.loc[self.SYMBOL_POS, 'positionAmt']

                # if not in position will proceed to buy
                if float(position_amount) == 0:
                    print('#################################')
                    print('BUY SIGNAL IS ON! Executing order')
                    print('#################################')
                    print("=========================================================")
                    entry_price1 = float(last_close)
                    entry_price = (round(entry_price1, self.round_off))
                    print("Entry Price at: {}".format(entry_price))

                    min_val = min(self.df_final['l'].tail(self.stop_csticks))
                    sl = float(min_val) - float(last_ATR)
                    stop_loss = (round(sl, self.round_off))
                    print("Calculated stop loss at: {}".format(stop_loss))

                    tp = (self.rrr * (entry_price - stop_loss)) + entry_price
                    take_profit = (round(tp, self.round_off))
                    print("Calculated take profit at: {}".format(take_profit))

                    SL_range = ((entry_price / stop_loss) - 1) * self.leverage
                    capital = self.risk_usd / SL_range

                    trade_quant = (capital * self.leverage) / entry_price
                    TRADE_QUANTITY = (round(trade_quant))
                    print("Trade Quantity: {}".format(TRADE_QUANTITY))
                    print("=========================================================")

                    try:
                        buy_limit_order = self.client.futures_create_order(symbol=self.TRADE_SYMBOL, side='BUY',
                                                                        type='LIMIT', timeInForce='GTC',
                                                                        price=entry_price, quantity=TRADE_QUANTITY)
                        order_id = buy_limit_order['orderId']
                        order_status = buy_limit_order['status']

                        timeout = time.time() + (50 * self.tme_frame)
                        while order_status != 'FILLED':
                            time.sleep(10)
                            order_status = self.client.futures_get_order(symbol=self.TRADE_SYMBOL, orderId=order_id)[
                                'status']
                            print(order_status)

                            if order_status == 'FILLED':
                                time.sleep(1)
                                set_stop_loss = self.client.futures_create_order(symbol=self.TRADE_SYMBOL, side='SELL',
                                                                                type='STOP_MARKET',
                                                                                quantity=TRADE_QUANTITY, stopPrice=stop_loss)
                                time.sleep(1)
                                set_take_profit = self.client.futures_create_order(symbol=self.TRADE_SYMBOL, side='SELL',
                                                                                type='TAKE_PROFIT_MARKET',
                                                                                quantity=TRADE_QUANTITY, stopPrice=take_profit)
                                break

                            if time.time() > timeout:
                                order_status = self.client.futures_get_order(symbol=self.TRADE_SYMBOL, orderId=order_id)[
                                    'status']

                                if order_status == 'PARTIALLY_FILLED':
                                    cancel_order = self.client.futures_cancel_order(symbol=self.TRADE_SYMBOL,
                                                                                    orderId=order_id)
                                    time.sleep(1)

                                    pos_size = self.client.futures_position_information()
                                    df = pd.DataFrame(pos_size)
                                    pos_amount = abs(float(df.loc[self.SYMBOL_POS, 'positionAmt']))

                                    time.sleep(1)
                                    set_stop_loss = self.client.futures_create_order(symbol=self.TRADE_SYMBOL, side='SELL',
                                                                                    type='STOP_MARKET',
                                                                                    quantity=pos_amount, stopPrice=stop_loss)
                                    time.sleep(1)
                                    set_take_profit = self.client.futures_create_order(symbol=self.TRADE_SYMBOL, side='SELL',
                                                                                    type='TAKE_PROFIT_MARKET',
                                                                                    quantity=pos_amount, stopPrice=take_profit)
                                    break

                                else:
                                    cancel_order = self.client.futures_cancel_order(symbol=self.TRADE_SYMBOL,
                                                                                    orderId=order_id)
                                    break

                    except BinanceAPIException as e:
                        # error handling goes here
                        print(e)
                    except BinanceOrderException as e:
                        # error handling goes here
                        print(e)
                else:
                    print("Buy long signal is on but you are already in position..")

            # Sell Condition
            if float(macd_3c_ago) > float(macdSignal_3c_ago) and float(last_macd) < float(last_macdSignal) and float(
                    macd_2c_ago) > 0 and float(last_close) < float(last_slowest_EMA) and float(
                last_close) < float(last_VWAP) and SL_range_sell <= self.stop_range:

                # condition 1: check if current balance is still above your risk
                now_balance = self.client.futures_account_balance()
                current_balance = now_balance[0]['balance']
                with open("current_balance.txt", "a+") as file_object:
                    file_object.seek(0)
                    data = file_object.read(100)
                    if len(data) > 0:
                        file_object.write("\n")
                    file_object.write(current_balance)
                with open('initial_balance.txt', 'r') as f:
                    lines = f.read().splitlines()
                    initial = float(lines[-1])
                with open('current_balance.txt', 'r') as f:
                    lines = f.read().splitlines()
                    current = float(lines[-1])

                    if (initial - (initial * self.risk_percent)) > current:
                        time.sleep(2)
                        sys.exit('Today is not your day. Bot is terminating.')

                time.sleep(1)

                # condition 2: check if in position
                check_if_in_position = self.client.futures_position_information()
                df = pd.DataFrame(check_if_in_position)
                position_amount = df.loc[self.SYMBOL_POS, 'positionAmt']

                if float(position_amount) == 0:
                    print('##################################')
                    print('SELL SIGNAL IS ON! Executing order')
                    print('##################################')
                    print("=========================================================")
                    entry_price1 = float(last_close)
                    entry_price = (round(entry_price1, self.round_off))
                    print("Entry Price at: {}".format(entry_price))

                    max_val = max(self.df_final['h'].tail(self.stop_csticks))
                    sl = float(max_val) + float(last_ATR)
                    stop_loss = (round(sl, self.round_off))
                    print("Calculated stop loss at: {}".format(stop_loss))

                    tp = (entry_price - (self.rrr * (stop_loss - entry_price)))
                    take_profit = (round(tp, self.round_off))
                    print("Calculated take profit at: {}".format(take_profit))

                    SL_range = ((stop_loss / entry_price) - 1) * self.leverage
                    capital = self.risk_usd / SL_range

                    trade_quant = (capital * self.leverage) / entry_price
                    TRADE_QUANTITY = (round(trade_quant))
                    print("Trade Quantity: {}".format(TRADE_QUANTITY))
                    print("=========================================================")

                    try:
                        sell_limit_order = self.client.futures_create_order(symbol=self.TRADE_SYMBOL, side='SELL',
                                                                            type='LIMIT', timeInForce='GTC',
                                                                            price=entry_price, quantity=TRADE_QUANTITY)
                        order_id = sell_limit_order['orderId']
                        order_status = sell_limit_order['status']

                        timeout = time.time() + (50 * self.tme_frame)
                        while order_status != 'FILLED':
                            time.sleep(10)  # check every 10sec if the limit order has been filled
                            order_status = self.client.futures_get_order(symbol=self.TRADE_SYMBOL, orderId=order_id)[
                                'status']
                            print(order_status)

                            if order_status == 'FILLED':
                                time.sleep(1)
                                set_stop_loss = self.client.futures_create_order(symbol=self.TRADE_SYMBOL, side='BUY',
                                                                                type='STOP_MARKET',
                                                                                quantity=TRADE_QUANTITY, stopPrice=stop_loss)
                                time.sleep(1)
                                set_take_profit = self.client.futures_create_order(symbol=self.TRADE_SYMBOL, side='BUY',
                                                                                type='TAKE_PROFIT_MARKET',
                                                                                quantity=TRADE_QUANTITY, stopPrice=take_profit)
                                break

                            if time.time() > timeout:
                                order_status = self.client.futures_get_order(symbol=self.TRADE_SYMBOL, orderId=order_id)[
                                    'status']

                                if order_status == 'PARTIALLY_FILLED':
                                    cancel_order = self.client.futures_cancel_order(symbol=self.TRADE_SYMBOL,
                                                                                   orderId=order_id)
                                    time.sleep(1)

                                    pos_size = self.client.futures_position_information()
                                    df = pd.DataFrame(pos_size)
                                    pos_amount = abs(float(df.loc[self.SYMBOL_POS, 'positionAmt']))

                                    time.sleep(1)
                                    set_stop_loss = self.client.futures_create_order(symbol=self.TRADE_SYMBOL, side='BUY',
                                                                                    type='STOP_MARKET',
                                                                                    quantity=pos_amount, stopPrice=stop_loss)
                                    time.sleep(1)
                                    set_take_profit = self.client.futures_create_order(symbol=self.TRADE_SYMBOL, side='BUY',
                                                                                    type='TAKE_PROFIT_MARKET',
                                                                                    quantity=pos_amount, stopPrice=take_profit)
                                    break

                                else:
                                    cancel_order = self.client.futures_cancel_order(symbol=self.TRADE_SYMBOL,
                                                                                    orderId=order_id)
                                    break


                    except BinanceAPIException as e:
                        # error handling goes here
                        print(e)
                    except BinanceOrderException as e:
                        # error handling goes here
                        print(e)
                else:
                    print("Sell short signal is on but you are already in position..")

        

if __name__ == "__main__":
    # Set the pair and time frame below
 
    symbol = 'btcusdt'
    tframe = '1m'
   
    leverage = 5  # leverage settings
    rrr = 2  # risk reward ratio
    risk = 0.25  # risk percent drop from initial balance stops the bot
    risk_usd = 200  # risk per trade in USD

    # stop loss settings
    stop_csticks = 10  # count n candlesticks backward for stop loss
    stop_range = 1

    # EMA and MACD default settings: 200, 12, 26, 9 respectively
    slowest_EMA = 200
    macd_fast = 12
    macd_slow = 20
    macd_signal = 9
    atr_period = 14
    # ===================================================================

    bot = CryptoBot(symbol, tframe, leverage, rrr, risk, risk_usd, stop_csticks, stop_range, slowest_EMA, macd_fast, macd_slow, macd_signal, atr_period)
    bot.initialize()
    bot.run_bot() 