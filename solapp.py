# solapp.py

from flask import Flask, render_template_string, request
import requests
import asyncio
import aiohttp

app = Flask(__name__)

SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
COINGECKO_SOL_PRICE_URL = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
SOLANA_TOKEN_LIST_URL = "https://raw.githubusercontent.com/solana-labs/token-list/main/src/tokens/solana.tokenlist.json"
JUPITER_PRICE_API_URL = "https://price.jup.ag/v1/price"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Solana Wallet Asset Viewer</title>
</head>
<body>
    <h1>Solana Wallet Asset Viewer</h1>
    <form method="POST">
        <label for="wallet">Enter Wallet Address:</label>
        <input type="text" id="wallet" name="wallet" placeholder="Enter Solana wallet address" required>
        <button type="submit">Check Assets</button>
    </form>
    {% if error %}
        <p style="color:red;">{{ error }}</p>
    {% endif %}
    {% if tokens %}
        <table border="1">
            <tr>
                <th>Token Name</th>
                <th>Mint Address</th>
                <th>Balance</th>
                <th>Price (USD)</th>
                <th>Dollar Value (USD)</th>
            </tr>
            {% for token in tokens %}
                <tr>
                    <td>{{ token.name }}</td>
                    <td>{{ token.mint_address }}</td>
                    <td>{{ token.balance }}</td>
                    <td>{{ token.price_usd }}</td>
                    <td>{{ token.dollar_value }}</td>
                </tr>
            {% endfor %}
        </table>
        <h2>Total Portfolio Value: {{ total_value }}</h2>
    {% endif %}
</body>
</html>
"""

def get_sol_balance(wallet_address):
    headers = {"Content-Type": "application/json"}
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [wallet_address]
    }
    try:
        response = requests.post(SOLANA_RPC_URL, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        lamports = result["result"]["value"]
        sol_balance = lamports / 1e9  # Convert lamports to SOL
        return sol_balance
    except Exception as e:
        print(f"Error fetching SOL balance: {e}")
        return None

def get_spl_tokens(wallet_address):
    headers = {"Content-Type": "application/json"}
    # Use getTokenAccountsByOwner with programId filter
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            wallet_address,
            {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
            {"encoding": "jsonParsed"}
        ]
    }
    try:
        response = requests.post(SOLANA_RPC_URL, json=payload, headers=headers)
        response.raise_for_status()
        result = response.json()
        tokens = []
        for token_account in result["result"]["value"]:
            account_data = token_account["account"]["data"]["parsed"]["info"]
            mint_address = account_data["mint"]
            token_amount = account_data.get("tokenAmount")
            if token_amount:
                balance = float(token_amount["amount"]) / (10 ** int(token_amount["decimals"]))
                if balance > 0:
                    tokens.append({
                        "mint_address": mint_address,
                        "balance": balance,
                        "decimals": token_amount["decimals"]
                    })
        return tokens
    except Exception as e:
        print(f"Error fetching SPL tokens: {e}")
        return []

def get_sol_price():
    try:
        response = requests.get(COINGECKO_SOL_PRICE_URL)
        response.raise_for_status()
        data = response.json()
        sol_price = data["solana"]["usd"]
        return sol_price
    except Exception as e:
        print(f"Error fetching SOL price: {e}")
        return None

def get_token_list():
    try:
        response = requests.get(SOLANA_TOKEN_LIST_URL)
        response.raise_for_status()
        data = response.json()
        tokens = data['tokens']
        return tokens
    except Exception as e:
        print(f"Error fetching token list from Solana Labs: {e}")
        return []

def map_mint_to_token_info(mint_addresses, token_list):
    token_info_map = {}
    for mint_address in mint_addresses:
        token_info = next((token for token in token_list if token['address'] == mint_address), None)
        if token_info:
            token_info_map[mint_address] = token_info
        else:
            token_info_map[mint_address] = {
                'name': f"SPL Token ({mint_address[:4]}...{mint_address[-4:]})",
                'symbol': ''
            }
    return token_info_map

async def fetch_jupiter_prices(session, mint_addresses):
    token_prices = {}
    for mint_address in mint_addresses:
        params = {'id': mint_address}
        try:
            async with session.get(JUPITER_PRICE_API_URL, params=params) as response:
                data = await response.json()
                price_info = data.get('data')
                if price_info:
                    price = price_info.get('price')
                    if price:
                        token_prices[mint_address] = price
        except Exception as e:
            print(f"Error fetching price from Jupiter for {mint_address}: {e}")
    return token_prices

async def get_all_token_prices(mint_addresses):
    async with aiohttp.ClientSession() as session:
        token_prices = await fetch_jupiter_prices(session, mint_addresses)
    return token_prices

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

        sol_balance = get_sol_balance(wallet_address)
        sol_price = get_sol_price()
        if sol_balance is not None and sol_price is not None:
            sol_value = sol_balance * sol_price
            if sol_balance > 0:  # Include SOL balance if greater than 0
                tokens.append({
                    "name": "Solana (SOL)",
                    "mint_address": "Native SOL",
                    "balance": f"{sol_balance:,.4f}",
                    "price_usd": f"${sol_price:,.2f}",
                    "dollar_value": f"${sol_value:,.2f}"
                })
                total_value += sol_value

        spl_tokens = get_spl_tokens(wallet_address)
        if spl_tokens:
            token_list = get_token_list()
            mint_addresses = [token['mint_address'] for token in spl_tokens]
            token_info_map = map_mint_to_token_info(mint_addresses, token_list)
            token_prices_data = asyncio.run(get_all_token_prices(mint_addresses))

            for token in spl_tokens:
                mint_address = token['mint_address']
                balance = token['balance']
                token_info = token_info_map.get(mint_address)
                token_name = token_info['name']
                symbol = token_info['symbol']

                price_usd = token_prices_data.get(mint_address)
                if price_usd:
                    dollar_value = balance * price_usd
                    total_value += dollar_value
                else:
                    dollar_value = None

                tokens.append({
                    "name": f"{token_name} ({symbol})",
                    "mint_address": mint_address,
                    "balance": f"{balance:,.4f}",
                    "price_usd": f"${price_usd:,.6f}" if price_usd else "N/A",
                    "dollar_value": f"${dollar_value:,.2f}" if dollar_value else "N/A"
                })

        tokens = sorted(tokens, key=lambda x: float(x["dollar_value"].replace("$", "").replace(",", "")) if x["dollar_value"] != "N/A" else 0, reverse=True)

    return render_template_string(
        HTML_TEMPLATE,
        tokens=tokens,
        total_value=f"${total_value:,.2f}",
        error=error_message
    )

if __name__ == "__main__":
    app.run(debug=True)
