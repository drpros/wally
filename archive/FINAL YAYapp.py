from flask import Flask, render_template_string, request
import requests

app = Flask(__name__)

# API Configurations
MORALIS_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJub25jZSI6IjczNmU3YTU5LWU3OGQtNDI0Ny1hMzQ3LTQ4MjYzYjIwMjVlOCIsIm9yZ0lkIjoiNDE1Nzc0IiwidXNlcklkIjoiNDI3MzEzIiwidHlwZSI6IlBST0pFQ1QiLCJ0eXBlSWQiOiJmZTEyZjFlNi02NTA5LTQ2MWEtODVhMy01Y2YzOTMxOWY2OTMiLCJpYXQiOjE3MzE5NTc3MzcsImV4cCI6NDg4NzcxNzczN30.9qNJbSylhelYu3inZmWRtXtR1PWWSgLoPIJwwcwsqPc"
ETHERSCAN_API_KEY = "G9Y9C9HZCJ754GF3CH3U9UIT5J5UF1983M"
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
        print(f"Ethereum price: ${eth_price}")
        return eth_price
    except Exception as e:
        print(f"Error fetching Ethereum price: {e}")
        return 1800  # Fallback to a default price if API fails

def get_eth_balance(wallet_address, eth_price):
    """Fetch Ethereum balance (ETH) using Moralis."""
    try:
        print(f"Fetching Ethereum balance for wallet: {wallet_address}")
        headers = {"X-API-Key": MORALIS_API_KEY}
        response = requests.get(f"{MORALIS_URL}/{wallet_address}/balance", headers=headers)
        response.raise_for_status()
        data = response.json()
        balance = int(data["balance"]) / 10**18  # Convert from Wei to ETH
        dollar_value = balance * eth_price
        if dollar_value > 5:  # Only include balances with dollar value > $5.00
            return {
                "name": "Ethereum (ETH)",
                "contract_address": wallet_address,
                "balance": f"{balance:,.4f}",
                "price_usd": f"${eth_price:,.2f}",
                "market_cap": "N/A",
                "dollar_value": f"${dollar_value:,.2f}",
            }
        return None
    except Exception as e:
        print(f"Error fetching Ethereum balance: {e}")
        return None

def get_erc20_balances(wallet_address):
    """Fetch ERC-20 token balances from Moralis."""
    try:
        print(f"Fetching ERC-20 balances for wallet: {wallet_address}")
        headers = {"X-API-Key": MORALIS_API_KEY}
        response = requests.get(f"{MORALIS_URL}/{wallet_address}/erc20", headers=headers)
        response.raise_for_status()
        tokens = []
        for token in response.json():
            balance = int(token["balance"]) / 10**int(token["decimals"])
            if balance > 0:  # Include tokens with a non-zero balance
                tokens.append({
                    "name": token.get("name", "Unknown Token"),
                    "contract_address": token.get("token_address"),
                    "balance": balance,
                })
        return tokens
    except Exception as e:
        print(f"Error fetching ERC-20 balances: {e}")
        return []

def get_market_data(contract_address):
    """Fetch market data (market cap and price) from DexScreener."""
    try:
        response = requests.get(f"{DEXSCREENER_URL}/{contract_address}")
        response.raise_for_status()
        data = response.json()
        if "pairs" in data and data["pairs"]:
            pair = data["pairs"][0]
            market_cap = pair.get("fdv")
            price_usd = float(pair.get("priceUsd", 0))
            return market_cap, price_usd
    except Exception as e:
        print(f"Error fetching market data for {contract_address}: {e}")
    return None, None

@app.route("/", methods=["GET", "POST"])
def index():
    tokens = []
    total_value = 0.0

    if request.method == "POST":
        wallet_address = request.form.get("wallet").strip()
        if not wallet_address:
            return render_template_string(HTML_TEMPLATE, tokens=[], total_value=f"${total_value:,.2f}")

        print(f"Checking assets for wallet: {wallet_address}")

        # Fetch Ethereum price
        eth_price = fetch_eth_price()

        # Fetch Ethereum balance
        eth_balance = get_eth_balance(wallet_address, eth_price)
        if eth_balance:
            tokens.append(eth_balance)
            total_value += float(eth_balance["dollar_value"].replace("$", "").replace(",", ""))

        # Fetch ERC-20 balances
        erc20_balances = get_erc20_balances(wallet_address)

        # Add market data and dollar value
        for token in erc20_balances:
            contract_address = token.get("contract_address")
            balance = token.get("balance")
            market_cap, price_usd = get_market_data(contract_address)

            if price_usd and (balance * price_usd) > 5.00:  # Filter tokens with dollar value <= $5.00
                dollar_value = balance * price_usd
                total_value += dollar_value

                tokens.append({
                    "name": token.get("name"),
                    "contract_address": contract_address,
                    "balance": f"{balance:,.4f}",
                    "price_usd": f"${price_usd:,.10f}" if price_usd and price_usd < 0.0001 else f"${price_usd:,.6f}" if price_usd else "N/A",
                    "market_cap": f"${market_cap:,.2f}" if market_cap else "N/A",
                    "dollar_value": f"${dollar_value:,.2f}" if dollar_value else "N/A",
                })

        # Sort tokens by dollar value in descending order
        tokens = sorted(tokens, key=lambda x: float(x.get("dollar_value", "0").replace("$", "").replace(",", "")) if x.get("dollar_value", "N/A") != "N/A" else 0, reverse=True)

    return render_template_string(HTML_TEMPLATE, tokens=tokens, total_value=f"${total_value:,.2f}")

if __name__ == "__main__":
    app.run(debug=True)
