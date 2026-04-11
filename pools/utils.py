import json
from datetime import datetime
import os

def write_json_token_entry(token: str, file = "tokens.txt"):
    entry = {
        "timestamp": datetime.now().isoformat(),
        "data": token
    }

    # If file exists, load existing data
    if os.path.exists(file):
        with open(file, "r") as f:
            entries = json.load(f)
    else:
        entries = []

    # Add new entry and save back to file
    entries.append(entry)
    with open(file, "w") as f:
        json.dump(entries, f, indent=4)