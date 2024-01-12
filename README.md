# Crypto Trading Bot

## Introduction

This Python script implements a basic crypto trading bot using the Binance API for futures trading. The bot is designed to execute buy and sell orders based on certain technical indicators and risk management parameters.

## Requirements

- Python 3
- Binance API key and secret (create one on the Binance platform)

## Setup

1. Install required packages:

   ```bash
   pip install websocket-client pandas talib python-binance

   Create a Binance API key and secret on the Binance platform.

Create a config.py file with your API key and secret:


# config.py
API_KEY = 'your_api_key'
API_SECRET = 'your_api_secret'
Modify the script's configuration:

Open the script (APP.py) and set the following parameters:

symbol: Trading symbol (e.g., 'btcusdt')
tframe: Time frame (e.g., '1m')
Adjust other parameters such as leverage, risk, stop settings, EMA, MACD, etc., based on your preferences.
Run the script:

bash
Features
The bot initializes by setting up leverage, checking account balances, and placing a test buy order.
It connects to the Binance WebSocket for real-time price data.
The trading strategy is based on EMA, MACD, and risk management parameters.
The bot can execute both buy and sell orders with take profit and stop loss.
Disclaimer
This script is provided for educational purposes only and does not guarantee profits. Use it at your own risk.

Author
Marsya Putra

License
This project is licensed under the MIT License.


Make sure to replace `"your_api_key"` and `"your_api_secret"` in the `config.py` section with your actual Binance API key and secret. Additionally, replace `[Your Name]` in the Author section with your name or username.
