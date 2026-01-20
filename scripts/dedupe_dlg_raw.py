"""
Deduplicate dlg_raw table in SQLite DB.
Keeps the row with the largest ROWID for each (lsp_id, lsp_name, lender, portfolio, as_on_timestamp).
Backs up the original table to dlg_raw_backup_<ts>.old before replacing.

Usage:
    python scripts/dedupe_dlg_raw.py [path/to/dlg_analysis.db]
"""
import sqlite3
import sys
import os
from datetime import datetime

DB = sys.argv[1] if len(sys.argv) > 1 else os.getenv('DLG_SQLITE_PATH', 'dlg_analysis.db')
if not os.path.exists(DB):
    print('DB not found:', DB)
    sys.exit(1)

conn = sqlite3.connect(DB)
cur = conn.cursor()

# count before
cur.execute('SELECT COUNT(*) FROM dlg_raw')
before = cur.fetchone()[0]
print('dlg_raw rows before:', before)

# backup original
ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
backup_name = f'dlg_raw_backup_{ts}_old'
print('Creating backup table', backup_name)
cur.execute(f'CREATE TABLE IF NOT EXISTS {backup_name} AS SELECT * FROM dlg_raw')
conn.commit()

# create dedup table
print('Creating dedup table dlg_raw_new...')
cur.execute('''
CREATE TABLE IF NOT EXISTS dlg_raw_new (
    lsp_id INTEGER,
    lsp_name TEXT,
    lender TEXT,
    portfolio TEXT,
    amount REAL,
    as_on_timestamp DATETIME,
    scrape_timestamp DATETIME,
    complete TEXT
)
''')
conn.commit()

# insert only rows with max ROWID per group
print('Inserting unique rows into dlg_raw_new...')
cur.execute('''
INSERT INTO dlg_raw_new
SELECT dr.lsp_id, dr.lsp_name, dr.lender, dr.portfolio, dr.amount, dr.as_on_timestamp, dr.scrape_timestamp, dr.complete
FROM dlg_raw dr
WHERE rowid IN (
    SELECT MAX(rowid) FROM dlg_raw
    GROUP BY lsp_id, lsp_name, lender, portfolio, as_on_timestamp
)
''')
conn.commit()

# counts
cur.execute('SELECT COUNT(*) FROM dlg_raw_new')
after = cur.fetchone()[0]
print('dlg_raw rows after dedupe:', after)

# swap tables
print('Dropping original dlg_raw and renaming dlg_raw_new to dlg_raw')
cur.executescript('''
DROP TABLE dlg_raw;
ALTER TABLE dlg_raw_new RENAME TO dlg_raw;
''')
conn.commit()

print('Done. Backup retained as table', backup_name)
conn.close()
