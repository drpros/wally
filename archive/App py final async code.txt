from flask import Flask, render_template_string, request
import asyncio
import aiohttp
import requests
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# API Configurations
MORALIS_API_KEY = os.getenv("MORALIS_API_KEY")
ETHERSCAN_API_KEY = os.getenv("ETHERSCAN_API_KEY")
MORALIS_URL = "https://deep-index.moralis.io/api/v2"
DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens"
COINGECKO_ETH_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Ethereum Wallet Asset Viewer</title>
</head>
<body>
    <h1>Ethereum Wallet Asset Viewer</h1>
    <form method="POST">
        <label for="wallet">Enter Wallet Address:</label>
        <input type="text" id="wallet" name="wallet" placeholder="0x..." required>
        <button type="submit">Check Assets</button>
    </form>
    {% if error %}
        <p style="color:red;">{{ error }}</p>
    {% endif %}
    {% if tokens %}
        <table border="1">
            <tr>
                <th>Token Name</th>
                <th>Contract Address</th>
                <th>Balance</th>
                <th>Price (USD)</th>
                <th>Market Cap (USD)</th>
                <th>Dollar Value (USD)</th>
            </tr>
            {% for token in tokens %}
                <tr>
                    <td>{{ token.name }}</td>
                    <td>{{ token.contract_address }}</td>
                    <td>{{ token.balance }}</td>
                    <td>{{ token.price_usd }}</td>
                    <td>{{ token.market_cap }}</td>
                    <td>{{ token.dollar_value }}</td>
                </tr>
            {% endfor %}
        </table>
        <h2>Total Portfolio Value: {{ total_value }}</h2>
    {% endif %}
</body>
</html>
"""

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
            if balance > 0:  # Skip tokens with zero balance
                tokens.append({
                    "name": token.get("name", "Unknown Token"),
                    "contract_address": token.get("token_address"),
                    "balance": balance,
                })
        return tokens
    except Exception:
        return []

async def fetch_market_data(session, contract_address):
    """Asynchronously fetch market data from DexScreener."""
    try:
        async with session.get(f"{DEXSCREENER_URL}/{contract_address}") as response:
            data = await response.json()
            if "pairs" in data and data["pairs"]:
                pair = data["pairs"][0]
                market_cap = pair.get("fdv")
                price_usd = float(pair.get("priceUsd", 0))
                return contract_address, market_cap, price_usd
    except Exception:
        pass
    return contract_address, None, None

async def get_all_market_data(contract_addresses):
    """Fetch market data for all tokens concurrently."""
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_market_data(session, addr) for addr in contract_addresses]
        results = await asyncio.gather(*tasks)
        return {addr: (market_cap, price_usd) for addr, market_cap, price_usd in results}

@app.route("/", methods=["GET", "POST"])
def index():
    tokens = []
    total_value = 0.0
    error_message = None

    if request.method == "POST":
        wallet_address = request.form.get("wallet").strip()
        if not wallet_address:
            error_message = "Please enter a wallet address."
            return render_template_string(HTML_TEMPLATE, tokens=[], total_value=f"${total_value:,.2f}", error=error_message)

        # Fetch Ethereum price
        eth_price = fetch_eth_price()

        # Fetch Ethereum balance
        eth_balance = get_eth_balance(wallet_address, eth_price)
        if eth_balance and float(eth_balance["dollar_value"].replace("$", "").replace(",", "")) > 5.00:
            tokens.append(eth_balance)
            total_value += float(eth_balance["dollar_value"].replace("$", "").replace(",", ""))

        # Fetch ERC-20 balances
        erc20_balances = get_erc20_balances(wallet_address)

        # Fetch market data concurrently
        contract_addresses = [token["contract_address"] for token in erc20_balances]
        market_data = asyncio.run(get_all_market_data(contract_addresses))

        # Add market data and dollar value
        for token in erc20_balances:
            contract_address = token["contract_address"]
            balance = token["balance"]
            market_cap, price_usd = market_data.get(contract_address, (None, None))

            dollar_value = balance * price_usd if price_usd else 0
            if dollar_value > 5.00:
                total_value += dollar_value
                tokens.append({
                    "name": token["name"],
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

    return render_template_string(
        HTML_TEMPLATE,
        tokens=tokens,
        total_value=f"${total_value:,.2f}",
        error=error_message
    )

if __name__ == "__main__":
    app.run(debug=True)
