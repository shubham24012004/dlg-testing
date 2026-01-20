"""Bulk import sources CSV into DB using DB managers (for test confirmation).
This script bypasses the HTTP API and writes directly to the DB managers.
"""
import sys
import os
import pandas as pd
from pathlib import Path
# ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from DatabaseOperation.SQLAlchemy.DatabaseModels import LspMaster, DlgCrawlerConfig
from General.Managers.LspMasterManagerDB import LspMasterManagerDB
from General.Managers.DlgCrawlerConfigManagerDB import DlgCrawlerConfigManagerDB

DB = Path("dlg_analysis.db")
CSV = Path("data/lsp_sources_latest.csv")

if not CSV.exists():
    print("CSV not found:", CSV)
    raise SystemExit(1)

cf = LspMasterManagerDB(str(DB))
cm = DlgCrawlerConfigManagerDB(str(DB))

print("Reading CSV...", CSV)
df = pd.read_csv(CSV, dtype=str).fillna("")

lsp_rows = []
config_rows = []
for _, row in df.iterrows():
    lsp_name = (row.get('lsp_name') or row.get('name') or '').strip()
    if not lsp_name:
        continue
    lsp_id = (row.get('lsp_id') or lsp_name).strip()
    disclosure_url = (row.get('disclosure_url') or row.get('dlg_url') or '').strip()
    is_active = str(row.get('is_active','')).strip().lower() in ('true','1','t','y','yes')
    fetch_hint = (row.get('fetch_hint') or 'auto').strip()
    parse_hint = (row.get('parse_hint') or 'auto').strip()
    rules_json = (row.get('rules_json') or '').strip() or None

    lsp = LspMaster(lsp_name=lsp_name, disclosure_url=disclosure_url, is_active=is_active, fetch_hint=fetch_hint, parse_hint=parse_hint, rules_json=rules_json, lsp_id=lsp_id, home_url=disclosure_url)
    lsp_rows.append(lsp)

    cfg = DlgCrawlerConfig(fetch_hint=fetch_hint, parse_hint=parse_hint, pre_click_js=None, rules_json=rules_json)
    config_rows.append((lsp_id, cfg, disclosure_url))

print(f"Importing {len(lsp_rows)} LSPs...")
count = cf.bulk_upsert(lsp_rows)
print("LSPs upserted:", count)

print(f"Importing {len(config_rows)} configs...")
count2 = cm.bulk_upsert(config_rows)
print("Configs upserted:", count2)
