# SolanaCopyBot

A bot that monitors Solana DEX programs in real-time via WebSocket, detects new liquidity pool creation events, and extracts token mint addresses from those transactions — intended as the foundation for a copy-trading system.

---

## Project Structure

```
SolanaCopyBot/
├── conf/                        # Configuration files
│   ├── keys.json                # API keys and WebSocket URLs (Helius) — not committed, see .gitignore
│   ├── programs.json            # DEX programs to monitor and their filters
│   └── info.json                # Known token mint addresses (SOL, WSOL)
│
├── pools/                       # Pool monitoring module
│   ├── websocket.py             # Core WebSocket listener and transaction parser
│   ├── utils.py                 # File I/O helpers
│   └── data/                   # Runtime data output
│       ├── data.json
│       ├── message.json
│       ├── tokens.txt           # Discovered token mints (JSON array)
│       ├── pool_data/           # Raw WebSocket log events per pool (keyed by sig prefix)
│       ├── tx_data/             # Raw full transaction data per signature
│       └── tx_ver/              # Verified/parsed transaction messages
│
├── defi/                        # DeFi utility module (WIP)
│   └── defi.py                  # Jupiter swap API constants and unit conversion helpers
│
├── requirements.txt             # Python dependencies
└── test.ipynb                   # Scratch notebook for experimentation
```

---

## Modules

### `pools/websocket.py` — Core Engine

The entry point when run directly (`python -m pools.websocket` or `__main__`).

#### `init()`
Loads config from `conf/` into module-level globals:
- `HELIUS_WS` — Helius WebSocket URL
- `PROGRAMS` — list of DEX program configs from `programs.json`
- `INFO` — token addresses from `info.json`

#### `monitor_programs(rpc_url)`
Top-level async runner. Opens an `AsyncClient` (Solana RPC) and a WebSocket connection to Helius, then calls `subscribe_to_programs` and `listen_for_events`.

#### `subscribe_to_programs(websocket)`
Iterates over `PROGRAMS` and sends a `logsSubscribe` JSON-RPC request for each program where `"track": true`. Subscribes to log events mentioning the program's public key with `finalized` commitment.

#### `listen_for_events(websocket, client)`
Async loop over incoming WebSocket messages:
1. Skips subscription confirmation messages.
2. For each log event, checks if any tracked program's `instruction_filter` string appears in the transaction logs.
3. On match, saves the raw event to `pools/data/pool_data/<sig[:4]>.json`.
4. Calls `fetch_transaction_details` to get full transaction data and extract token mints.
5. If a mint is found, writes it to `tokens.txt` via `write_json_token_entry`.

#### `fetch_transaction_details(program, sig_str, client)`
Given a transaction signature:
1. Fetches the full transaction via `client.get_transaction` with `jsonParsed` encoding.
2. Saves raw data to `pools/data/tx_data/<sig[:4]>.json`.
3. Extracts the first account from the matching program instruction — treated as the pool account.
4. Calls `client.get_account_info` on the pool account.
5. Decodes the raw account bytes and extracts:
   - **Token A mint**: bytes `[8:40]` — Base58 encoded
   - **Token B mint**: bytes `[40:72]` — Base58 encoded

> Note: The commented-out code shows an earlier approach that used parsed SPL associated token account instructions to find mints and validate against SOL/WSOL. The current approach reads raw account data directly.

---

### `pools/utils.py` — File Utilities

#### `write_json_token_entry(token, file)`
Appends a timestamped token entry to a JSON array file:
```json
[
  { "timestamp": "2025-01-01T00:00:00", "data": "<mint_address>" }
]
```
Creates the file if it doesn't exist.

---

### `defi/defi.py` — DeFi Helpers (WIP)

Contains constants and unit conversion utilities for swap execution via the Jupiter Aggregator API. Not yet integrated into the main flow.

| Name | Description |
|---|---|
| `JUPITER_QUOTE_API` | Jupiter v6 quote endpoint |
| `JUPITER_SWAP_API` | Jupiter v6 swap endpoint |
| `INPUT_MINT` | Hardcoded SOL mint (input token for swaps) |
| `lamp_to_sol(lamp)` | Convert lamports → SOL |
| `sol_to_lamp(sol)` | Convert SOL → lamports |
| `slip_to_bps(slip)` | Convert slippage % → basis points |
| `bps_to_slip(bps)` | Convert basis points → slippage % |

---

## Configuration

### `conf/programs.json`
Defines which Solana programs to subscribe to:

| Program | Label | Tracked |
|---|---|---|
| `675kPX9...` | Raydium LP V4 Pool | No |
| `pAMMBay6...` | PumpFun AMM | **Yes** |
| `CPMMoo8L...` | Raydium CPMM | No |

Each entry has:
- `program_id` — the on-chain program public key
- `instruction_filter` — a string to match against transaction logs to identify the target instruction (e.g. `"Instruction: CreatePool"`)
- `label` — human-readable name
- `track` — whether to actively monitor this program

### `conf/keys.json`
Not committed. Create this file locally with your own credentials (see `.gitignore`).

### `conf/info.json`
Known token mint addresses used for validation:
- `SOL` — native SOL mint
- `WSOL` — wrapped SOL mint

---

## Dependencies

```
solders      # Rust-backed Solana types (Pubkey, Signature, etc.)
solana       # Solana Python SDK (AsyncClient, RPC methods)
websockets   # Async WebSocket client
```

Install with:
```bash
pip install -r requirements.txt
```

---

## Running

```bash
python pools/websocket.py
```

The bot will:
1. Connect to the Helius WebSocket endpoint
2. Subscribe to `logsSubscribe` for all tracked programs
3. On each `CreatePool` event, fetch the full transaction, parse the pool account data, and save discovered token mints to `pools/data/tokens.txt`

---

## Data Flow

```
Helius WebSocket
      |
      | logsSubscribe (finalized)
      v
listen_for_events()
      |
      | instruction_filter match
      v
fetch_transaction_details()
      |
      | get_transaction() → get_account_info()
      v
Extract Token A & B mints from raw account bytes
      |
      v
write_json_token_entry() → pools/data/tokens.txt
```
