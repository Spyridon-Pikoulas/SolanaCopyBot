import os
from solana.rpc.async_api import AsyncClient
from websockets import connect
import json
from solders.pubkey import Pubkey
from websockets.exceptions import ConnectionClosed, WebSocketException
from solana.rpc.commitment import Finalized
from solders.rpc.responses import GetTransactionResp
import asyncio
from solders.signature import Signature
from pools.utils import write_json_token_entry
from datetime import datetime
import base58
import base64

async def fetch_transaction_details(program: str, sig_str: str, client: AsyncClient):
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
        with open(f"pools/data/tx_data/{sig_str[:4]}.json", "w") as f:
            json.dump(tx, f, indent=4)
        print("Got transaction details for signature:", sig_str[:4])

        # There is no transaction data
        if tx.get("result") is None:
            print(f"No result found for {sig_str[:4]}")
            return None
        if "transaction" not in tx["result"]:
            print(f"No transaction found in result for {sig_str[:4]}")
            return None
        
        # Get message data
        msg = tx["result"]["transaction"]["message"]
        msg["time"] = datetime.now().isoformat()
        with open(f"pools/data/tx_ver/{sig_str[:4]}.json", "w") as f:
            json.dump(tx, f, indent=4)
        
        # Get account info
        instructions = msg["instructions"]
        for ins in instructions:
            if ins.get("programId", "") != program:
                continue
            accounts = ins.get("accounts", [])
            if not accounts:
                raise ValueError("No accounts found in transaction instructions")
            pool_account = accounts[0]  # Assuming the first account is the pool account
            break

        print(f"Pool account: {pool_account}")
        pool_account_resp = await client.get_account_info(Pubkey.from_string(pool_account))
        print(f"Pool account data from {sig_str[:4]}...:\n", pool_account_resp)
        bytes_data = pool_account_resp.value.data
        bytes_data = base64.b64decode(bytes_data)
        token_a_mint_bytes = bytes_data[8:40]
        token_a_mint = base58.b58encode(token_a_mint_bytes).decode()
        # Extract Token B (assuming associated token account, bytes 40-71)
        token_b_bytes = bytes_data[40:72]
        token_b = base58.b58encode(token_b_bytes).decode()
        x=3
        # mints = []
        # for ins in instructions:
        #     program = ins.get("program", "")
        #     if program != "spl-associated-token-account":
        #         continue
        #     parsed = ins.get("parsed", {})
        #     if not parsed:
        #         continue
        #     mint = parsed.get("mint", {})
        #     if not mint:
        #         continue

        #     mints.append(mint)

        # mints = list(set(mints))
        # if not ((INFO["SOL"] in mints) or (INFO["WSOL"] in mints)):
        #     print("Warning: No SOL mint found in transaction!")
        #     return None
        # if len(mints) != 2:
        #     print("More or less mints found than expected:\n", mints)
        #     return None

        # mints.remove("So11111111111111111111111111111111111111112")
        # mint = mints[0]

        # # Extract mint authority
        # resp = client.get_account_info(Pubkey.from_string(mint))
        # if resp.value:
        #     byte_list = resp.value.data
        #     if len(byte_list) < 36:
        #         raise ValueError("Invalid mint account data length")
        #     authority_bytes = byte_list[4:36]
        #     mint_authority = Pubkey(bytes(authority_bytes))
        #     print("Mint authority:", mint_authority)
        # else:
        #     print("No account data found.")
        #     return None

        # if mint_authority != "TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM":
        #     mint = None

        # return mint

    except BaseException as e:
        print(f"Error fetching transaction details for {sig_str[:4]}: {e}\n")
        print("Transaciton:\n", tx)
        return None


async def subscribe_to_programs(websocket):
    """Subscribe to Solana programs for log events."""
    for program in PROGRAMS:
        if not program["track"]:
            continue
        print(f"Subscribing to program: {program['label']})")
        program_id = program["program_id"]
        subscription_request = {
            "jsonrpc": "2.0",
            "id": PROGRAMS.index(program) + 1,
            "method": "logsSubscribe",
            "params": [{"mentions": [program_id]}, {"commitment": "finalized"}],
        }
        try:
            await websocket.send(json.dumps(subscription_request))
            print(f"Subscribed to program: {program['label']} ({program_id})")
        except (ConnectionClosed, WebSocketException) as e:
            print(f"Failed to subscribe to {program['label']} ({program_id}): {e}")
            continue
        except Exception as e:
            print(
                f"Unexpected error subscribing to {program['label']} ({program_id}): {e}"
            )
            continue


async def listen_for_events(websocket, client):
    try:
        async for message in websocket:
            data = json.loads(message)  # It does not contain the token adress

            # Subscription confirmation
            if "result" in data and isinstance(data["result"], int):
                # Initial subscription confirmation
                print(f"Subscription ID: {data['result']}")
                continue

            # There is data
            if "params" in data and "result" in data["params"]:
                result = data["params"]["result"]
                signature = result["value"]["signature"]
                logs = result["value"]["logs"]

                # Find which program triggered this transaction
                for program in PROGRAMS:
                    if program["track"] is False:
                        continue
                    program_id = program["program_id"]
                    instruction_filter = program["instruction_filter"]
                    label = program["label"]

                    # Check if program ID is mentioned in logs
                    if any(instruction_filter in l for l in logs):
                        print("Received CreatePool event! for program:", label)
                        with open(
                            f"pools/data/pool_data/{signature[:4]}.json", "w"
                        ) as f:
                            json.dump(data, f, indent=4)

                        output_mint = await fetch_transaction_details(
                            program_id, signature, client
                        )
                        if output_mint is not None:
                            print(f"Outputa mint found: {output_mint}")
                            write_json_token_entry(output_mint, "tokens.txt")
                    break

    except BaseException as e:
        print(f"WebSocket connection failed: {e}")
        # with open("data.json", "w") as f:
        #     json.dump(all_data, f, indent=4)

    # with open("data.json", "w") as f:
    #     json.dump(all_data, f, indent=4)


async def monitor_programs(rpc_url="https://api.mainnet-beta.solana.com"):
    """Monitor Solana programs with reconnection logic."""
    try:
        async with AsyncClient(rpc_url) as client:
            async with connect(HELIUS_WS) as websocket:
                await subscribe_to_programs(websocket)
                await listen_for_events(websocket, client)
    except KeyboardInterrupt:
        print("Program stopped by user, closing connection...")
    except Exception as e:
        print(f"WebSocket connection failed: {e}")


def init():
    # Init
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    # HELIUS_WS
    global HELIUS_WS
    with open(os.path.join(project_root, "conf/keys.json")) as f:
        keys = f.read()
    keys = json.loads(keys)
    HELIUS_WS = keys["Helius_WS"]

    # PROGRAMS
    global PROGRAMS
    with open(os.path.join(project_root, "conf/programs.json")) as f:
        programs = f.read()
    PROGRAMS = json.loads(programs)["programs"]

    # INFO
    global INFO
    with open(os.path.join(project_root, "conf/info.json")) as f:
        info = f.read()
    INFO = json.loads(info)


if __name__ == "__main__":
    init()
    asyncio.run(monitor_programs())
