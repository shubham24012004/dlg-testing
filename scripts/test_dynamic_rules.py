"""
Test script for LSP dynamic rules from CSV configuration.
Usage: python scripts/test_dynamic_rules.py [--lsp <name_filter>]
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from General.Service.DlgCrawlerService import DlgCrawlerService
from utils.logger_config import logger_method

logger = logger_method(__name__)

# Simple mock object for testing (avoids SQLAlchemy/database)
@dataclass
class MockLspMaster:
    id: int
    name: str
    home_url: str
    active: bool
    dlg_url: str
    parse_hint: str
    fetch_hint: str
    rules_json: Optional[str]
    last_crawl_date: Optional[datetime] = None

def main():
    parser = argparse.ArgumentParser(description='Test LSP crawling with dynamic rules')
    parser.add_argument('--lsp', type=str, help='Filter LSP by name (case-insensitive substring match)')
    parser.add_argument('--csv', type=str, default='lsp_master_works_3_fully_dynamic.csv', 
                        help='CSV file with LSP configurations')
    args = parser.parse_args()

    print("Starting test run...")
    
    # Resolve CSV path
    csv_path = Path(__file__).parent.parent / args.csv
    if not csv_path.exists():
        print(f"ERROR: CSV file not found: {csv_path}")
        sys.exit(1)
    
    print(f"Using CSV file: {csv_path}")
    
    if args.lsp:
        print(f"Filtering for LSP: {args.lsp}")
        print("-" * 30)
    
    # Read LSP configurations
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        lsps = list(reader)
    
    logger.info(f"Read {len(lsps)} LSPs from {csv_path}")
    
    # Filter if requested
    if args.lsp:
        filter_lower = args.lsp.lower()
        lsps = [lsp for lsp in lsps if filter_lower in lsp['name'].lower()]
        logger.info(f"Filtering for LSP: {args.lsp}")
    
    if not lsps:
        print(f"No LSPs found matching filter: {args.lsp}")
        sys.exit(1)
    
    # Test each LSP
    for lsp in lsps:
        print("\n" + "=" * 80)
        logger.info(f"Testing: {lsp['name']}")
        logger.info(f"URL: {lsp['dlg_url']}")
        
        # Parse rules if present
        rules_json = lsp.get('rules_json', '').strip()
        if rules_json:
            logger.info(f"rules_json received (str): {rules_json[:200]}...")
            try:
                rules = json.loads(rules_json)
                logger.info(f"Rules loaded (dict): {rules}")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse rules_json: {e}")
                continue
        
        # Check for pre_click_js
        pre_click_js = None
        if rules_json:
            try:
                rules = json.loads(rules_json)
                pre_click_js = rules.get('pre_click_js')
                if pre_click_js:
                    logger.info(f"pre_click_js from rules: {pre_click_js[:100]}...")
                else:
                    logger.info("pre_click_js from rules: None")
            except:
                logger.info("pre_click_js from rules: None")
        
        # Create mock LSP object (avoids database)
        lsp_obj = MockLspMaster(
            id=0,  # Test ID
            name=lsp['name'],
            home_url=lsp.get('home_url', ''),
            active=True,
            dlg_url=lsp['dlg_url'],
            parse_hint=lsp.get('parse_hint', 'auto'),
            fetch_hint=lsp.get('fetch_hint', 'auto'),
            rules_json=rules_json if rules_json else None
        )
        
        # Execute crawl using the service
        logger.info(f"_execute_fetch: fetch_hint={lsp_obj.parse_hint}, pre_click_js={'Yes' if pre_click_js else 'None'}")
        
        try:
            service = DlgCrawlerService()
            print(f"\n>>> DEBUG: Calling scrape_one with:")
            print(f"    parse_hint: {lsp_obj.parse_hint}")
            print(f"    fetch_hint: {lsp_obj.fetch_hint}")
            print(f"    rules_json length: {len(lsp_obj.rules_json) if lsp_obj.rules_json else 0}")
            
            status, error_msg, raw_html, rows = service.scrape_one(lsp_obj)
            
            print(f"\n>>> DEBUG: scrape_one returned:")
            print(f"    status: {status}")
            print(f"    rows: {len(rows)}")
            
            logger.info(f"PDF extraction returned {len(rows)} raw rows")
            if rows:
                logger.info(f"First raw row keys: {list(rows[0].keys())}")
                logger.info(f"First raw row: {rows[0]}")
            
            logger.info(f"Raw rows before normalization: {len(rows)}")
            logger.info(f"After normalization: {len(rows)} rows, status: {status}")
            
            if rows:
                logger.info(f"SUCCESS ({status}): Extracted {len(rows)} rows for {lsp['name']}")
                
                # Show sample data
                print(json.dumps(rows, indent=2, default=str))
                
            else:
                logger.warning(f"No rows extracted for {lsp['name']}")
                
        except Exception as e:
            logger.error(f"ERROR testing {lsp['name']}: {e}", exc_info=True)
    
    print("\n" + "=" * 80)
    logger.info("Test script finished.")

if __name__ == '__main__':
    main()
