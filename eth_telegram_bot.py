import os
import requests
import asyncio
import aiohttp
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    filters,
    MessageHandler
)
from dotenv import load_dotenv
import logging

# Load environment variables from .env file
load_dotenv()

# Fetch API keys from environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")

# API URLs
MORALIS_URL = "https://deep-index.moralis.io/api/v2"
DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens"
COINGECKO_ETH_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message when the command /start is issued."""
    await update.message.reply_text(
        'Welcome to the Ethereum Wallet Scanner Bot!\n\n'
        'Send me an Ethereum wallet address using the /wallet command, '
        'and I will provide you with the wallet\'s ETH balance and ERC-20 token balances along with their USD values.\n\n'
        'Example:\n/wallet 0xYourEthereumWalletAddressHere'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a help message when the command /help is issued."""
    await update.message.reply_text(
        'To use this bot, send an Ethereum wallet address using the /wallet command.\n\n'
        'Example:\n/wallet 0xYourEthereumWalletAddressHere'
    )

def fetch_eth_price():
    """Fetch the current price of Ethereum (ETH) in USD from CoinGecko."""
    try:
        response = requests.get(COINGECKO_ETH_PRICE_URL)
        response.raise_for_status()
        data = response.json()
        eth_price = data["ethereum"]["usd"]
        return eth_price
    except Exception:
        return 1800  # Fallback price if API fails

def get_eth_balance(wallet_address, eth_price):
    """Fetch Ethereum balance (ETH) using Moralis."""
    try:
        headers = {"X-API-Key": MORALIS_API_KEY}
        response = requests.get(f"{MORALIS_URL}/{wallet_address}/balance", headers=headers)
        response.raise_for_status()
        data = response.json()
        balance = int(data["balance"]) / 10**18  # Convert from Wei to ETH
        dollar_value = balance * eth_price
        return {
            "name": "Ethereum (ETH)",
            "contract_address": wallet_address,
            "balance": f"{balance:,.4f}",
            "price_usd": f"${eth_price:,.2f}",
            "market_cap": "N/A",
            "dollar_value": f"${dollar_value:,.2f}",
        }
    except Exception:
        return None

def get_erc20_balances(wallet_address):
    """Fetch ERC-20 token balances from Moralis."""
    try:
        headers = {"X-API-Key": MORALIS_API_KEY}
        response = requests.get(f"{MORALIS_URL}/{wallet_address}/erc20", headers=headers)
        response.raise_for_status()
        tokens = []
        for token in response.json():
            balance = int(token["balance"]) / 10**int(token["decimals"])
            if balance > 0:
                tokens.append({
                    "name": token.get("name", "Unknown Token"),
                    "symbol": token.get("symbol", ""),
                    "contract_address": token.get("token_address"),
                    "balance": balance,
                })
        return tokens
    except Exception:
        return []

def fetch_market_data_sync(contract_address):
    """Fetch market data (market cap and price) from DexScreener synchronously."""
    try:
        response = requests.get(f"{DEXSCREENER_URL}/{contract_address}")
        response.raise_for_status()
        data = response.json()
        if "pairs" in data and data["pairs"]:
            pair = data["pairs"][0]
            market_cap = pair.get("fdv")
            price_usd = float(pair.get("priceUsd", 0))
            return market_cap, price_usd
    except Exception:
        pass
    return None, None

def get_all_market_data_sync(contract_addresses):
    """Fetch market data for all contract addresses synchronously."""
    market_data = {}
    for address in contract_addresses:
        market_cap, price_usd = fetch_market_data_sync(address)
        market_data[address] = (market_cap, price_usd)
    return market_data

async def wallet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /wallet command to scan Ethereum wallet addresses."""
    if context.args:
        wallet_address = context.args[0]
    else:
        await update.message.reply_text('Please provide an Ethereum wallet address.\n\nExample:\n/wallet 0xYourEthereumWalletAddressHere')
        return

    # Validate Ethereum address format
    if not (wallet_address.startswith('0x') and len(wallet_address) == 42):
        await update.message.reply_text('Please provide a valid Ethereum wallet address (starts with 0x and is 42 characters long).')
        return

    await update.message.reply_text(f'Scanning wallet: {wallet_address}\nPlease wait...')

    # Fetch Ethereum price
    eth_price = fetch_eth_price()

    # Fetch Ethereum balance
    eth_balance = get_eth_balance(wallet_address, eth_price)
    tokens = []
    total_value = 0.0
    if eth_balance and float(eth_balance["dollar_value"].replace("$", "").replace(",", "")) > 5.00:
        tokens.append(eth_balance)
        total_value += float(eth_balance["dollar_value"].replace("$", "").replace(",", ""))

    # Fetch ERC-20 balances
    erc20_balances = get_erc20_balances(wallet_address)
    contract_addresses = [token["contract_address"] for token in erc20_balances]
    market_data = get_all_market_data_sync(contract_addresses)

    for token in erc20_balances:
        contract_address = token["contract_address"]
        balance = token["balance"]
        market_cap, price_usd = market_data.get(contract_address, (None, None))

        dollar_value = balance * price_usd if price_usd else 0
        if dollar_value > 5.00:
            total_value += dollar_value
            tokens.append({
                "name": token["name"],
                "symbol": token["symbol"],
                "contract_address": contract_address,
                "balance": f"{balance:,.4f}",
                "price_usd": f"${price_usd:,.10f}" if price_usd and price_usd < 0.0001 else f"${price_usd:,.6f}" if price_usd else "N/A",
                "market_cap": f"${market_cap:,.2f}" if market_cap else "N/A",
                "dollar_value": f"${dollar_value:,.2f}",
            })

    # Sort tokens by dollar value in descending order
    tokens = sorted(
        tokens,
        key=lambda x: float(x.get("dollar_value", "0").replace("$", "").replace(",", "")),
        reverse=True
    )

    # Build the message
    if tokens:
        message = f"ETH Balance: {eth_balance['balance']} ETH (Value: {eth_balance['dollar_value']})\n\n"
        for token in tokens:
            message += (
                f"- {token['name']}\n  Contract Address: {token['contract_address']}\n  Balance: {token['balance']}\n  Price (USD): {token['price_usd']}\n  Market Cap (USD): {token['market_cap']}\n  Dollar Value (USD): {token['dollar_value']}\n\n"
            )
        message += f"Total Portfolio Value: ${total_value:,.2f}"
    else:
        message = 'No tokens found with a value greater than $5.00.'

    await update.message.reply_text(message, parse_mode='Markdown')

def main():
    """Start the Telegram bot."""
    # Ensure that the TELEGRAM_BOT_TOKEN is set
    if not TELEGRAM_BOT_TOKEN:
        logging.error('TELEGRAM_BOT_TOKEN is not set. Please set it in the .env file.')
        return

    # Create the Application
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('wallet', wallet_command))

    # Run the bot
    application.run_polling()

if __name__ == '__main__':
    main()
