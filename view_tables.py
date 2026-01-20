# view_tables.py
import sqlite3
import pandas as pd
import webbrowser
from pathlib import Path

DB = Path("dlg_analysis.db")
con = sqlite3.connect(DB)
tables = ["dlg_raw", "audit_log", "lsp_master", "dlg_crawler_config"]

# Print concise summaries to console
for t in tables:
    try:
        df = pd.read_sql_query(f"SELECT * FROM {t} LIMIT 200", con)
        print(f"\n=== {t} (rows: {len(df)}) ===")
        if not df.empty:
            print(df.head(20).to_string(index=False))
        else:
            print("(empty or table missing)")
    except Exception as e:
        print(f"{t} error: {e}")

# Render a single HTML page with all tables for easier browsing
parts = [
    "<html><head><meta charset='utf-8'><title>DLG DB Tables</title>\n",
    "<style>body{font-family:Arial,Helvetica,sans-serif;padding:16px}table{border-collapse:collapse;width:100%;margin-bottom:24px}th,td{border:1px solid #ddd;padding:8px;text-align:left}th{background:#f4f4f4}</style>",
    "</head><body>",
    f"<h1>Database: {DB.name}</h1>\n",
]

for t in tables:
    try:
        df = pd.read_sql_query(f"SELECT * FROM {t} LIMIT 1000", con)
        parts.append(f"<h2>{t} (rows: {len(df)})</h2>")
        if not df.empty:
            parts.append(df.to_html(index=False, classes='table', border=0, justify='left'))
        else:
            parts.append("<p><em>(empty or missing)</em></p>")
    except Exception as e:
        parts.append(f"<h2>{t}</h2><p><em>error: {e}</em></p>")

parts.append("</body></html>")

out = Path("dlg_db_tables.html")
out.write_text("\n".join(parts), encoding="utf-8")
webbrowser.open(out.resolve().as_uri())

con.close()
