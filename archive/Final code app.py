from flask import Flask, render_template_string, request
import requests

app = Flask(__name__)

# API configurations
ETHERSCAN_API_KEY = "G9Y9C9HZCJ754GF3CH3U9UIT5J5UF1983M"
MORALIS_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJub25jZSI6IjczNmU3YTU5LWU3OGQtNDI0Ny1hMzQ3LTQ4MjYzYjIwMjVlOCIsIm9yZ0lkIjoiNDE1Nzc0IiwidXNlcklkIjoiNDI3MzEzIiwidHlwZSI6IlBST0pFQ1QiLCJ0eXBlSWQiOiJmZTEyZjFlNi02NTA5LTQ2MWEtODVhMy01Y2YzOTMxOWY2OTMiLCJpYXQiOjE3MzE5NTc3MzcsImV4cCI6NDg4NzcxNzczN30.9qNJbSylhelYu3inZmWRtXtR1PWWSgLoPIJwwcwsqPc"
MORALIS_URL = "https://deep-index.moralis.io/api/v2"
ETHERSCAN_URL = "https://api.etherscan.io/api"
DEXSCREENER_URL = "https://api.dexscreener.com/latest/dex/tokens"

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
        <h2>Token Holdings</h2>
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
    {% endif %}
</body>
</html>
"""

def get_erc20_balances(wallet_address):
    """Fetch ERC-20 token balances from Moralis."""
    try:
        print(f"Fetching ERC-20 balances for wallet: {wallet_address}")
        headers = {"X-API-Key": MORALIS_API_KEY}
        url = f"{MORALIS_URL}/{wallet_address}/erc20"
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        tokens = []
        for token in response.json():
            balance = int(token["balance"]) / 10**int(token["decimals"])
            if balance > 0:
                tokens.append({
                    "name": token.get("name", "Unknown Token"),
                    "contract_address": token.get("token_address"),
                    "balance": balance,
                    "symbol": token.get("symbol", "Unknown Symbol"),
                })
        return tokens
    except Exception as e:
        print(f"Error fetching ERC-20 balances: {e}")
        return []

def fetch_dexscreener_metadata(contract_address):
    """Fetch price and market cap from DexScreener."""
    try:
        url = f"{DEXSCREENER_URL}/{contract_address}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        if "pairs" in data and data["pairs"]:
            pair_data = data["pairs"][0]
            price_usd = float(pair_data.get("priceUsd", 0))
            market_cap = pair_data.get("fdv", None)
            return price_usd, market_cap
        return None, None
    except Exception as e:
        print(f"Error fetching data from DexScreener for {contract_address}: {e}")
        return None, None

@app.route("/", methods=["GET", "POST"])
def index():
    tokens = []

    if request.method == "POST":
        wallet_address = request.form.get("wallet").strip()
        if not wallet_address:
            return render_template_string(HTML_TEMPLATE, tokens=[])

        print(f"Checking assets for wallet: {wallet_address}")

        # Fetch ERC-20 balances
        erc20_balances = get_erc20_balances(wallet_address)

        # Fetch price, market cap, and dollar value
        for token in erc20_balances:
            contract_address = token.get("contract_address")
            price_usd, market_cap = fetch_dexscreener_metadata(contract_address)
            dollar_value = token["balance"] * price_usd if price_usd else 0

            tokens.append({
                "name": token["name"],
                "contract_address": contract_address,
                "balance": f"{token['balance']:,.4f}",
                "price_usd": f"${price_usd:,.10f}" if price_usd else "N/A",
                "market_cap": f"${market_cap:,.2f}" if market_cap else "N/A",
                "dollar_value": f"${dollar_value:,.2f}" if dollar_value else "N/A",
            })

    return render_template_string(HTML_TEMPLATE, tokens=tokens)

if __name__ == "__main__":
    app.run(debug=True)
