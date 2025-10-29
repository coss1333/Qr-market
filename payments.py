# payments.py (demo-grade; replace with indexer-backed checks in production)
import os
from datetime import datetime
from dotenv import load_dotenv
from web3 import Web3
from tronpy import Tron
from db import database
from models import qr_lots

load_dotenv()
BSC_RPC = os.environ.get("BSC_RPC")
TRON_NODE = os.environ.get("TRON_NODE")

w3 = None
tron = None

def init_blockchain_clients():
    global w3, tron
    if BSC_RPC:
        w3 = Web3(Web3.HTTPProvider(BSC_RPC, request_kwargs={'timeout': 10}))
    if TRON_NODE:
        tron = Tron(network=TRON_NODE)

async def check_pending_payments():
    rows = await database.fetch_all(qr_lots.select().where(qr_lots.c.status == "awaiting_payment"))
    results = []
    for r in rows:
        status = await _check_single_lot(r)
        results.append((r["id"], status))
    return results

def check_pending_payments_sync():
    import asyncio
    return asyncio.get_event_loop().run_until_complete(check_pending_payments())

async def _check_single_lot(row):
    lot_id = row["id"]
    price = row["price"]
    currency = (row["currency"] or "").upper()
    token_contract = row["token_contract"]
    target_addr = row["receive_address"]

    try:
        if currency.startswith("BEP") or currency.startswith("BSC"):
            paid = await _check_bsc(target_addr, token_contract, price)
        elif currency.startswith("TRC"):
            paid = await _check_tron(target_addr, token_contract, price)
        else:
            return "unknown_currency"
    except Exception as e:
        return f"error:{e}"

    if paid:
        await database.execute(
            qr_lots.update().where(qr_lots.c.id==lot_id).values(status="paid", updated_at=datetime.utcnow())
        )
        return "paid"
    return "not_paid"

async def _check_bsc(target, token_contract, price_amount):
    if not w3:
        return False
    target = Web3.toChecksumAddress(target)
    if not token_contract:
        # naive scan of last ~500 blocks for native BNB transfers
        latest = w3.eth.block_number
        start = max(0, latest-500)
        for bn in range(latest, start, -1):
            block = w3.eth.get_block(bn, full_transactions=True)
            for tx in block.transactions:
                if tx.to and tx.to == target:
                    val = float(w3.fromWei(tx.value, 'ether'))
                    if val + 1e-12 >= float(price_amount):
                        return True
        return False
    else:
        # ERC20 Transfer(to=target)
        erc20_abi = [{
            "anonymous": False,
            "inputs": [
                {"indexed": True, "internalType": "address", "name": "from", "type": "address"},
                {"indexed": True, "internalType": "address", "name": "to", "type": "address"},
                {"indexed": False, "internalType": "uint256", "name": "value", "type": "uint256"}
            ],
            "name": "Transfer",
            "type": "event"
        },{
            "constant": True, "inputs": [], "name": "decimals", "outputs": [{"name":"","type":"uint8"}], "type":"function"
        }]
        token = w3.eth.contract(address=Web3.toChecksumAddress(token_contract), abi=erc20_abi)
        latest = w3.eth.block_number
        from_block = max(0, latest-5000)
        try:
            events = token.events.Transfer.create_filter(
                fromBlock=from_block, toBlock=latest, argument_filters={'to': target}
            ).get_all_entries()
        except Exception:
            # fallback to get_logs
            topic = Web3.keccak(text="Transfer(address,address,uint256)").hex()
            logs = w3.eth.get_logs({
                "fromBlock": from_block,
                "toBlock": latest,
                "address": Web3.toChecksumAddress(token_contract),
                "topics": [topic, None, Web3.keccak(hexstr=target.lower().replace('0x','').rjust(64,'0')).hex() if False else None]
            })
            events = []
        decimals = 18
        try:
            decimals = token.functions.decimals().call()
        except Exception:
            pass
        for ev in events:
            val = ev['args']['value'] / (10 ** decimals)
            if val + 1e-12 >= float(price_amount):
                return True
        return False

async def _check_tron(target, token_contract, price_amount):
    # NOTE: tronpy without an indexer is limited. For production, use TronGrid events:
    #   https://api.trongrid.io/v1/contracts/{token}/events?event_name=Transfer&limit=200&sort=-block_timestamp&filter=to=={target}
    # Here we leave a stub returning False to avoid false positives.
    return False
