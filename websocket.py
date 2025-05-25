from solana.rpc.async_api import AsyncClient
from websockets import connect
import json
from solders.pubkey import Pubkey
from websockets.exceptions import ConnectionClosed, WebSocketException
from solana.rpc.commitment import Finalized
from solders.rpc.responses import GetTransactionResp
import asyncio
from solders.signature import Signature
from utils import write_json_token_entry
from datetime import datetime

with open("keys.json") as f:
    keys = f.read()
keys = json.loads(keys)
helius_ws = keys["Helius_WS"]


PROGRAMS_TO_MONITOR = [
    {
        "program_id": "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
        "instruction_filter": "initialize2: InitializeInstruction2",
        "label": "Raydium LP V4 Pool",
        "track": False,
    },
    {
        "program_id": "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",
        "instruction_filter": "Instruction: CreatePool",
        "label": "PumpFun AMM",
        "track": True,
    },
    {
        "program_id": "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C",
        "instruction_filter": "initialize2: InitializeInstruction2",
        "label": "Raydium CPMM",
        "track": False,
    },
]

async def fetch_transaction_details(
    program, sig_str: str, client: AsyncClient, program_id, label: str
):
    """Fetch and parse transaction details for a given signature."""
    try:
        sig_encoded = Signature.from_string(sig_str)
        tx = await client.get_transaction(
                sig_encoded,
                commitment=Finalized,
                max_supported_transaction_version=0,
                encoding="jsonParsed",
            )
        tx = json.loads(tx.to_json())
        print("Got transaction details for signature:", sig_str)
        if "transaction" not in tx["result"]:
            return None
        msg = tx["result"]["transaction"]["message"]
        msg["time"] = datetime.now().isoformat()
        with open(f"pool_messages/{sig_str[:4]}.json", "w") as f:
            json.dump(msg, f, indent=4)

        instructions = msg["instructions"]
        mints = []
        for ins in instructions:
            program = ins.get("program", "")
            if program != "spl-associated-token-account":
                continue
            parsed = ins.get("parsed", {})
            if not parsed:
                continue    
            info = parsed.get("info", {})
            source = info.get("source", "")
            if (not info) or (not source):
                print(f"Skipping instruction with missing data: {parsed}")
                continue

            mint = info.get("mint")
            mints.append(mint)
        
        mints = list(set(mints))
        if not "So11111111111111111111111111111111111111112" in mints:
            print("Warning: No SOL mint found in transaction!")
            return None
        if len(mints) != 2:
            print("More or less mints found than expected:\n", mints)
            return None
        
        mints.remove("So11111111111111111111111111111111111111112")
        mint = mints[0]

        # Extract mint authority
        resp = client.get_account_info(Pubkey.from_string(mint))
        if resp.value:
            byte_list = resp.value.data
            if len(byte_list) < 36:
                raise ValueError("Invalid mint account data length")
            authority_bytes = byte_list[4:36]
            mint_authority = Pubkey(bytes(authority_bytes))
            print("Mint authority:", mint_authority)
        else:
            print("No account data found.")
            return None
        
        if mint_authority != "TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM":
            mint = None
        
        return mint
                


    except BaseException as e:
        print(f"Error fetching transaction details for {sig_str}: {e}")
        print("Transaciton:\n", tx)
        print("Message:\n", msg)
        return None


async def subscribe_to_programs(websocket, programs):
    """Subscribe to Solana programs for log events."""
    for program in PROGRAMS_TO_MONITOR:
        if not program["track"]:
            continue
        print(f"Subscribing to program: {program['label']})")
        program_id = program["program_id"]
        subscription_request = {
            "jsonrpc": "2.0",
            "id": PROGRAMS_TO_MONITOR.index(program) + 1,
            "method": "logsSubscribe",
            "params": [{"mentions": [program_id]}, {"commitment": "finalized"}],
        }
        try:
            await websocket.send(json.dumps(subscription_request))
            print(f"Subscribed to program: {program['label']} ({program_id})")
        except (ConnectionClosed, WebSocketException) as e:
            print(f"Failed to subscribe to {program['label']} ({program_id}): {e}")
            continue  # Skip to next program
        except Exception as e:
            print(
                f"Unexpected error subscribing to {program['label']} ({program_id}): {e}"
            )
            continue


async def listen_for_events(websocket, client, programs):
    all_data = []
    try:
        async for message in websocket:
            # print(f"Received message!")
            data = json.loads(message)
            if "result" in data and isinstance(data["result"], int):
                # Initial subscription confirmation
                print(f"Subscription ID: {data['result']}")
                continue
            if "params" in data and "result" in data["params"]:
                result = data["params"]["result"]
                signature = result["value"]["signature"]
                logs = result["value"]["logs"]

                # Find which program triggered this transaction
                for program in programs:
                    if program["track"] is False:
                        continue
                    program_id = program["program_id"]
                    instruction_filter = program["instruction_filter"]
                    label = program["label"]

                    # Check if program ID is mentioned in logs
                    if any(instruction_filter in l for l in logs):
                        print("Received CreatePool event!")
                        all_data.append(data)
                        output_mint = await fetch_transaction_details(
                            program_id, signature, client, program_id, label
                        )
                        if output_mint is not None:
                            print(f"Output mint found: {output_mint}")
                            write_json_token_entry(output_mint, "tokens.txt")

    except BaseException as e:
        print(f"WebSocket connection failed: {e}")
        with open("data.json", "w") as f:
            json.dump(all_data, f, indent=4)

    with open("data.json", "w") as f:
        json.dump(all_data, f, indent=4)


async def monitor_programs(
    programs, helius_ws, rpc_url="https://api.mainnet-beta.solana.com"
):
    """Monitor Solana programs with reconnection logic."""
    try:
        async with AsyncClient(rpc_url) as client:
            async with connect(helius_ws) as websocket:
                await subscribe_to_programs(websocket, programs)
                await listen_for_events(websocket, client, programs)
    except KeyboardInterrupt:
        print("Program stopped by user, closing connection...")
    except Exception as e:
        print(f"WebSocket connection failed: {e}")


if __name__ == "__main__":
    asyncio.run(monitor_programs(PROGRAMS_TO_MONITOR, helius_ws))
