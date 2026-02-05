#!/usr/bin/env python3
"""Save current index snapshot for intraday review table"""
import json, requests
from datetime import datetime
from pathlib import Path

SNAPSHOT_FILE = Path(__file__).parent.parent / "data/snapshots/intraday/today_index_snapshots.json"
SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)

# Load existing
if SNAPSHOT_FILE.exists():
    snapshots = json.loads(SNAPSHOT_FILE.read_text())
    if snapshots.get("date") != datetime.now().strftime("%Y-%m-%d"):
        snapshots = {"date": datetime.now().strftime("%Y-%m-%d"), "snapshots": []}
else:
    snapshots = {"date": datetime.now().strftime("%Y-%m-%d"), "snapshots": []}

# Get current index data
indexes = {}
for code in ["000001.SH", "399001.SZ", "399006.SZ"]:
    try:
        resp = requests.get(f"http://127.0.0.1:8000/api/index/realtime/{code}", timeout=5)
        if resp.ok:
            d = resp.json()
            indexes[code] = {
                "name": d.get("name", code),
                "price": round(d.get("price", d.get("close", 0)), 2),
                "pct": round(d.get("pct_change", d.get("change_pct", 0)), 2)
            }
    except:
        pass

if indexes:
    snapshots["snapshots"].append({
        "time": datetime.now().strftime("%H:%M"),
        "indexes": indexes
    })
    SNAPSHOT_FILE.write_text(json.dumps(snapshots, ensure_ascii=False, indent=2))
    print(f"Saved {datetime.now().strftime('%H:%M')}, total: {len(snapshots['snapshots'])}")
