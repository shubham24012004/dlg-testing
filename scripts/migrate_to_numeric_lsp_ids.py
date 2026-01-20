"""
Migration script to convert `lsp_master` string PKs into numeric autoincrement IDs
and update dependent tables (`dlg_crawler_config`, `dlg_raw`, `audit_log`).

Run: python scripts/migrate_to_numeric_lsp_ids.py [path/to/dlg_analysis.db]
If no path provided, defaults to `dlg_analysis.db` in repo root.
"""
import sqlite3
import sys
import os

DB = sys.argv[1] if len(sys.argv) > 1 else os.getenv('DLG_SQLITE_PATH', 'dlg_analysis.db')

def table_has_column(conn, table, column):
    cur = conn.execute(f"PRAGMA table_info('{table}')")
    cols = [r[1] for r in cur.fetchall()]
    return column in cols

def main():
    if not os.path.exists(DB):
        print('DB not found:', DB)
        return
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # detect current lsp_master id column type
    cur.execute("PRAGMA table_info('lsp_master')")
    cols = cur.fetchall()
    col_names = [r[1] for r in cols]
    print('lsp_master columns:', col_names)

    if table_has_column(conn, 'lsp_master', 'legacy_id'):
        print('Migration already applied (legacy_id exists). Exiting.')
        conn.close()
        return

    # Begin migration
    print('Creating new lsp_master_new...')
    cur.executescript('''
    CREATE TABLE lsp_master_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        legacy_id TEXT UNIQUE,
        name TEXT NOT NULL,
        home_url TEXT,
        active INTEGER
    );

    INSERT INTO lsp_master_new (legacy_id, name, home_url, active)
    SELECT id, name, home_url, CASE WHEN active IN (1,'1','true','True') THEN 1 ELSE 0 END FROM lsp_master;
    ''')
    print('lsp_master migrated.')

    print('Creating dlg_crawler_config_new...')
    cur.executescript('''
    CREATE TABLE dlg_crawler_config_new (
        lsp_id INTEGER PRIMARY KEY,
        dlg_url TEXT NOT NULL,
        is_active INTEGER,
        parse_hint TEXT,
        fetch_hint TEXT,
        rules_json TEXT,
        last_crawl_date DATETIME
    );

    INSERT INTO dlg_crawler_config_new (lsp_id, dlg_url, is_active, parse_hint, fetch_hint, rules_json, last_crawl_date)
    SELECT (
        SELECT id FROM lsp_master_new WHERE legacy_id = dlg_crawler_config.lsp_id LIMIT 1
    ), dlg_url, is_active, parse_hint, fetch_hint, rules_json, last_crawl_date
    FROM dlg_crawler_config
    WHERE (SELECT id FROM lsp_master_new WHERE legacy_id = dlg_crawler_config.lsp_id LIMIT 1) IS NOT NULL;
    ''')
    print('dlg_crawler_config migrated.')

    # dlg_raw
    print('Creating dlg_raw_new...')
    cur.executescript('''
    CREATE TABLE dlg_raw_new (
        lsp_id INTEGER,
        lsp_name TEXT,
        lender TEXT,
        portfolio TEXT,
        amount REAL,
        as_on_timestamp DATETIME,
        scrape_timestamp DATETIME,
        complete TEXT
    );

    INSERT INTO dlg_raw_new (lsp_id, lsp_name, lender, portfolio, amount, as_on_timestamp, scrape_timestamp, complete)
    SELECT (
        SELECT id FROM lsp_master_new WHERE legacy_id = dlg_raw.lsp_id LIMIT 1
    ), lsp_name, lender, portfolio, amount, as_on_timestamp, scrape_timestamp, complete
    FROM dlg_raw
    ;
    ''')
    print('dlg_raw migrated.')

    # audit_log
    print('Creating audit_log_new...')
    cur.executescript('''
    CREATE TABLE audit_log_new (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lsp_id INTEGER,
        legacy_lsp_id TEXT,
        auto_manual TEXT,
        user_id TEXT,
        payload TEXT,
        action_taken TEXT
    );

    INSERT INTO audit_log_new (lsp_id, legacy_lsp_id, auto_manual, user_id, payload, action_taken)
    SELECT (
        SELECT id FROM lsp_master_new WHERE legacy_id = audit_log.lsp_id LIMIT 1
    ), audit_log.lsp_id, audit_log.auto_manual, audit_log.user_id, audit_log.payload, audit_log.action_taken
    FROM audit_log;
    ''')
    print('audit_log migrated.')

    # rename/drop
    print('Dropping old tables and renaming new ones...')
    cur.executescript('''
    DROP TABLE dlg_crawler_config;
    ALTER TABLE dlg_crawler_config_new RENAME TO dlg_crawler_config;

    DROP TABLE dlg_raw;
    ALTER TABLE dlg_raw_new RENAME TO dlg_raw;

    DROP TABLE audit_log;
    ALTER TABLE audit_log_new RENAME TO audit_log;

    DROP TABLE lsp_master;
    ALTER TABLE lsp_master_new RENAME TO lsp_master;
    ''')

    conn.commit()
    conn.close()
    print('Migration complete.')

if __name__ == '__main__':
    main()
