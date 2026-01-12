import os
import csv
import datetime as dt
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
from models import FetchResult, SourceRow
from utils import parse_bool, extract_from_pdf, extract_from_html_tables, extract_dlg_from_plain_text, looks_like_pdf, \
    normalize_rows
from content_fetchers import fetch_with_requests

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False


def fetch_with_playwright(url: str, timeout_ms: int = 60000) -> FetchResult:
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("Playwright not installed/available. Install playwright to scrape JS-rendered pages.")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        html = page.content().encode("utf-8", errors="ignore")
        browser.close()
        return FetchResult(url=url, status_code=200, content_type="text/html; charset=utf-8", body=html,
                           fetch_mode_used="playwright")


# -----------------------------
# LSP MASTER CSV LOADER
# -----------------------------

def load_master_csv(path: str) -> List[SourceRow]:
    df = pd.read_csv(path, dtype=str).fillna("")
    out: List[SourceRow] = []
    for _, r in df.iterrows():
        lsp_name = r.get("lsp_name", "").strip()
        url = r.get("disclosure_url", "").strip()
        if not lsp_name or not url:
            continue
        out.append(SourceRow(
            lsp_name=lsp_name,
            disclosure_url=url,
            is_active=parse_bool(r.get("is_active", "true")),
            fetch_hint=(r.get("fetch_hint", "auto").strip() or "auto"),
            parse_hint=(r.get("parse_hint", "auto").strip() or "auto"),
            rules_json=(r.get("rules_json", "").strip() or None)
        ))
    return out


# -----------------------------
# SCRAPE ONE SOURCE (auto fallback)
# -----------------------------

def scrape_one(src: SourceRow) -> Tuple[str, Optional[str], Optional[str], List[Dict[str, Any]]]:
    scrape_ts = dt.datetime.utcnow()
    url = src.disclosure_url
    fetch_hint = (src.fetch_hint or "auto").lower()
    parse_hint = (src.parse_hint or "auto").lower()

    fetch: Optional[FetchResult] = None

    # Fetch (requests retry happens inside decorator)
    if fetch_hint == "playwright":
        fetch = fetch_with_playwright(url)
    else:
        fetch = fetch_with_requests(url)

    if fetch.status_code >= 400:
        raise RuntimeError(f"HTTP {fetch.status_code}")

    # Parse
    raw_rows: List[Dict[str, Any]] = []
    if parse_hint == "plain_text":
        raw_rows = extract_dlg_from_plain_text(fetch.body, lsp_name=src.lsp_name, scrape_ts=scrape_ts)
    elif parse_hint == "pdf_table" or looks_like_pdf(fetch):
        raw_rows = extract_from_pdf(fetch)
    elif parse_hint == "html_table":
        raw_rows = extract_from_html_tables(fetch)
    else:
        # auto
        if looks_like_pdf(fetch):
            raw_rows = extract_from_pdf(fetch)
        else:
            raw_rows = extract_from_html_tables(fetch)

            # If no rows, try JS fallback
            if not raw_rows and PLAYWRIGHT_AVAILABLE and fetch.fetch_mode_used != "playwright":
                fetch_pw = fetch_with_playwright(url)
                raw_rows = extract_from_html_tables(fetch_pw)
                fetch = fetch_pw

    normalized, status = normalize_rows(
        raw_rows=raw_rows,
        fetch=fetch,
        lsp_name=src.lsp_name,
        scrape_ts=scrape_ts,
        rules_json=src.rules_json
    )

    if status:
        return "Partial", fetch.fetch_mode_used, fetch.content_type, normalized
    elif not status:
        return "Completed", fetch.fetch_mode_used, fetch.content_type, normalized

    return "Missing", fetch.fetch_mode_used, fetch.content_type, []


# -----------------------------
# RAW CSV WRITER (CSV "DB")
# -----------------------------

RAW_COLUMNS = ["LSP Name", "Lender", "Portfolio", "Amount", "AsOnTimestamp", "ScrapeTimestamp", "Complete"]


def append_raw_rows(raw_csv_path: str, rows: List[Dict[str, Any]]) -> None:
    file_exists = os.path.exists(raw_csv_path)

    with open(raw_csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=RAW_COLUMNS)

        if not file_exists:
            writer.writeheader()

        for r in rows:
            # Convert datetime to ISO strings for CSV
            ason = r.get("AsOnTimestamp")
            scrape = r.get("ScrapeTimestamp")

            writer.writerow({
                "LSP Name": r.get("LSP Name"),
                "Lender": r.get("Lender"),
                "Portfolio": r.get("Portfolio"),
                "Amount": r.get("Amount"),
                "AsOnTimestamp": ason.strftime("%Y-%m-%d") if isinstance(ason, dt.datetime) else (
                    ason if ason else None),
                "ScrapeTimestamp": scrape.strftime("%Y-%m-%d %H:%M:%S") if isinstance(scrape, dt.datetime) else (
                    scrape if scrape else None),
                "Complete": r.get("Complete")
            })


def run_scrape(master_csv: str, raw_csv: str, limit: Optional[int] = None) -> None:
    sources = [s for s in load_master_csv(master_csv) if s.is_active]
    if limit:
        sources = sources[:limit]

    for src in sources:
        scrape_ts = dt.datetime.utcnow()
        try:
            complete_flag, _, _, rows = scrape_one(src)

            if complete_flag == "Completed":
                out = []
                for r in rows:
                    out.append({
                        **r,
                        "Complete": "Completed"
                    })
                append_raw_rows(raw_csv, out)

            elif complete_flag == "Partial":
                out = []
                for r in rows:
                    out.append({
                        **r,
                        "Complete": "Partial"
                    })
                append_raw_rows(raw_csv, out)

            elif complete_flag == "Missing":
                append_raw_rows(raw_csv, [{
                    "LSP Name": src.lsp_name,
                    "Lender": None,
                    "Portfolio": None,
                    "Amount": None,
                    "AsOnTimestamp": None,
                    "ScrapeTimestamp": scrape_ts,
                    "Complete": "Missing"
                }])

            print(f"[OK] {src.lsp_name} -> {complete_flag}")

        except Exception as e:
            append_raw_rows(raw_csv, [{
                "LSP Name": src.lsp_name,
                "Lender": None,
                "Portfolio": None,
                "Amount": None,
                "AsOnTimestamp": None,
                "ScrapeTimestamp": scrape_ts,
                "Complete": "Error"
            }])
            print(f"[ERR] {src.lsp_name} -> Error ({str(e)[:120]})")


# -----------------------------
# CLI
# -----------------------------

if __name__ == "__main__":
    ip_master_csv = "data\\lsp_sources.csv"
    op_raw_csv = "data\\dlg_raw.csv"
    run_scrape(ip_master_csv, op_raw_csv)
