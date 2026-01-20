# query_db.py
import sqlite3
import json
from pathlib import Path

DB = Path("dlg_analysis.db")  # change if you set DLG_SQLITE_PATH

if not DB.exists():
    print(f"No DB found at {DB.resolve()}")
    raise SystemExit(1)

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
cur = con.cursor()

def show(title, rows):
    print(f"\n--- {title} ({len(rows)} rows shown) ---")
    for r in rows:
        print(dict(r))

# list tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
tables = [t[0] for t in cur.fetchall()]
print("Tables:", tables)

# sample dlg_raw
try:
    cur.execute("SELECT * FROM dlg_raw ORDER BY scrape_timestamp DESC LIMIT 20;")
    rows = cur.fetchall()
    show("dlg_raw (latest 20)", rows)
except Exception as e:
    print("dlg_raw query error:", e)

# sample audit_log
try:
    cur.execute("SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 20;")
    rows = cur.fetchall()
    show("audit_log (latest 20)", rows)
except Exception as e:
    print("audit_log query error:", e)

# distinct action_taken values
try:
    cur.execute("SELECT DISTINCT action_taken FROM audit_log;")
    vals = [r[0] for r in cur.fetchall()]
    print("\nDistinct action_taken:", vals)
except Exception as e:
    print("distinct action_taken query error:", e)

con.close()