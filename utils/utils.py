from __future__ import annotations

import re
import io
import json
import datetime as dt
import calendar
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from typing import Any, Dict, List, Optional, Tuple
import pdfplumber
import requests
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

BROWSER_HEADERS = {
    "User-Agent": BROWSER_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
}


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=12))
def fetch_with_requests(url: str, timeout: int = 40) -> FetchResult:
    from DatabaseOperation.DatabaseModels.master_models import FetchResult
    r = requests.get(url, headers=BROWSER_HEADERS, timeout=timeout, allow_redirects=True)
    ct = r.headers.get("content-type", "") or ""
    return FetchResult(url=url, status_code=r.status_code, content_type=ct, body=r.content,
                       fetch_mode_used="requests")


def fetch_with_playwright(url: str, timeout_ms: int = 60_000,
                          pre_click_js: str | None = None,
                          wait_ms: int = 0) -> FetchResult:
    from DatabaseOperation.DatabaseModels.master_models import FetchResult
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("Playwright not installed/available. Install playwright to scrape JS-rendered pages.")
    try:
        header_overrides = {k: v for k, v in BROWSER_HEADERS.items() if k.lower() != "user-agent"}
        with sync_playwright() as context_manager:
            browser = context_manager.chromium.launch(headless=True,
                                                      args=["--disable-blink-features=AutomationControlled"])
            context = browser.new_context(user_agent=BROWSER_USER_AGENT, extra_http_headers=header_overrides)
            page = context.new_page()
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)

            final_url = url
            if pre_click_js:
                # Execute JavaScript - it may return a URL to navigate to
                result = page.evaluate(pre_click_js)

                # If JavaScript returns a URL string, handle it appropriately
                if result and isinstance(result, str) and (
                        result.startswith('http://') or result.startswith('https://')):
                    final_url = result

                    # If it's a PDF, close browser and download directly
                    if final_url.lower().endswith('.pdf'):
                        context.close()
                        browser.close()
                        headers = {**BROWSER_HEADERS, "User-Agent": BROWSER_USER_AGENT}
                        response = requests.get(final_url, headers=headers, timeout=40)
                        return FetchResult(
                            url=final_url,
                            status_code=response.status_code,
                            content_type="application/pdf",
                            body=response.content,
                            fetch_mode_used="playwright+requests",
                        )
                    else:
                        # Navigate to the returned URL (non-PDF)
                        page.goto(final_url, wait_until="networkidle", timeout=timeout_ms)
                else:
                    # JavaScript didn't return a URL, just wait for any navigation it triggered
                    try:
                        page.wait_for_load_state("networkidle", timeout=5000)
                    except:
                        pass

                page.wait_for_timeout(2000)
                final_url = page.url

            # Check if we're on a PDF page
            if final_url.lower().endswith('.pdf'):
                # We're on a PDF - download it using requests
                context.close()
                browser.close()
                headers = {**BROWSER_HEADERS, "User-Agent": BROWSER_USER_AGENT}
                response = requests.get(final_url, headers=headers, timeout=40)
                return FetchResult(
                    url=final_url,
                    status_code=response.status_code,
                    content_type="application/pdf",
                    body=response.content,
                    fetch_mode_used="playwright+requests",
                )

            # Otherwise return HTML content
            if wait_ms > 0:
                page.wait_for_timeout(wait_ms)
            html = page.content().encode("utf-8", errors="ignore")
            context.close()
            browser.close()
            return FetchResult(
                url=final_url,
                status_code=200,
                content_type="text/html; charset=utf-8",
                body=html,
                fetch_mode_used="playwright",
            )
    except Exception as ex:
        raise RuntimeError(f"Failed to fetch page with Playwright: {ex}")


def _clean_html_to_text(html: bytes) -> str:
    soup = BeautifulSoup(html, "html.parser")
    # drop script/style
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text("\n", strip=True)
    # normalize whitespace
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def parse_bool(x: Any) -> bool:
    return str(x).strip().lower() in ("true", "1", "t", "yes", "y")


# noinspection PyBroadException
def parse_date_any(s: Any) -> Optional[dt.datetime]:
    try:
        if s is None:
            return None
        txt = str(s).strip()
        if not txt:
            return None

        # Remove ordinal suffixes (1st, 2nd, 3rd, 4th, etc.) to help dateparser
        txt_cleaned = re.sub(r'(\d+)(?:st|nd|rd|th)\b', r'\1', txt)

        # Detect Month-YYYY format (e.g., "Jan-2026") before preprocessing
        month_yyyy_match = re.search(r"([A-Za-z]{3,9})-(\d{4})\b", txt_cleaned)

        # Handle Month-YYYY format (e.g., "Jan-2026" -> "Jan 2026")
        txt_cleaned = re.sub(r"([A-Za-z]{3,9})-(\d{4})\b", r"\1 \2", txt_cleaned)

        # Detect Month'YY format before preprocessing
        # Includes regular apostrophe ('), left quote (\u2018), and right quote (\u2019)
        month_yy_match = re.search(r"([A-Za-z]{3,9})[''\u2018\u2019](\d{2})\b", txt_cleaned)

        # Handle Month'YY format (e.g., "Dec'25" -> "Dec 2025")
        txt_cleaned = re.sub(r"([A-Za-z]{3,9})[''\u2018\u2019](\d{2})\b", r"\1 20\2", txt_cleaned)

        # Handle DD-Month-YY format (e.g., "31-January-26" -> "31-January-2026")
        txt_cleaned = re.sub(r"(\d{1,2})-([A-Za-z]{3,9})-(\d{2})\b", r"\1-\2-20\3", txt_cleaned)

        try:
            parsed = dateparser.parse(txt_cleaned, dayfirst=True, fuzzy=True)

            # If we parsed a Month'YY or Month-YYYY format, set to last day of that month
            # (Financial disclosures with "as on Dec'25" or "as on Jan-2026" mean end of month)
            if parsed and (month_yy_match or month_yyyy_match):
                last_day = calendar.monthrange(parsed.year, parsed.month)[1]
                parsed = parsed.replace(day=last_day)

            return parsed
        except Exception:
            return None
    except Exception:
        return None


def calculate_previous_month_end(reference_date: Optional[dt.datetime] = None) -> dt.datetime:
    """Calculate the last day of the previous month relative to reference_date."""
    if reference_date is None:
        reference_date = dt.datetime.now()

    # First day of current month
    first_of_month = reference_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Last day of previous month
    last_day_prev_month = first_of_month - dt.timedelta(days=1)
    return last_day_prev_month


def calculate_previous_quarter_end(reference_date: Optional[dt.datetime] = None) -> dt.datetime:
    """Calculate the last day of the previous quarter (Mar 31, Jun 30, Sep 30, Dec 31)."""
    if reference_date is None:
        reference_date = dt.datetime.now()

    # Determine current quarter
    current_month = reference_date.month
    if current_month <= 3:
        # Q1 (Jan-Mar) -> previous quarter is Q4 of previous year (Dec 31)
        return dt.datetime(reference_date.year - 1, 12, 31)
    elif current_month <= 6:
        # Q2 (Apr-Jun) -> previous quarter is Q1 (Mar 31)
        return dt.datetime(reference_date.year, 3, 31)
    elif current_month <= 9:
        # Q3 (Jul-Sep) -> previous quarter is Q2 (Jun 30)
        return dt.datetime(reference_date.year, 6, 30)
    else:
        # Q4 (Oct-Dec) -> previous quarter is Q3 (Sep 30)
        return dt.datetime(reference_date.year, 9, 30)


def parse_date_with_format(date_string: str, format_hint: str) -> Optional[dt.datetime]:
    """
    Parse date string with a format hint.
    
    Format hints:
    - DD.MM.YYYY: 31.12.2025
    - DD-MM-YYYY: 31-12-2025
    - DD Month YYYY: 31 December 2025, 31 Dec 2025
    - Mon YYYY: Dec 2025 (parsed to last day of month if to_day='last' in config)
    """
    if not date_string:
        return None

    date_string = date_string.strip()

    # Try format-specific parsing
    if format_hint == "DD.MM.YYYY":
        # Match DD.MM.YYYY
        match = re.match(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', date_string)
        if match:
            day, month, year = match.groups()
            try:
                return dt.datetime(int(year), int(month), int(day))
            except ValueError:
                pass

    elif format_hint == "DD-MM-YYYY":
        # Match DD-MM-YYYY
        match = re.match(r'(\d{1,2})-(\d{1,2})-(\d{4})', date_string)
        if match:
            day, month, year = match.groups()
            try:
                return dt.datetime(int(year), int(month), int(day))
            except ValueError:
                pass

    elif format_hint in ["DD Month YYYY", "DD Month YYYY with ordinal"]:
        # Remove ordinal suffixes (st, nd, rd, th)
        cleaned = re.sub(r'(\d+)(?:st|nd|rd|th)', r'\1', date_string)
        # Try parsing with dateparser
        try:
            return dateparser.parse(cleaned, dayfirst=True)
        except Exception:
            pass

    elif format_hint == "Mon YYYY":
        # Parse month name and year, return last day of that month
        try:
            parsed = dateparser.parse(date_string, dayfirst=True)
            if parsed:
                # Get last day of the month
                next_month = parsed.replace(day=28) + dt.timedelta(days=4)
                last_day = next_month - dt.timedelta(days=next_month.day)
                return last_day.replace(hour=0, minute=0, second=0, microsecond=0)
        except Exception:
            pass

    # Fallback to general parsing
    return parse_date_any(date_string)


def parse_amount_any(s: Any) -> Optional[float]:
    if s is None:
        return None
    txt = str(s).strip()
    if not txt:
        return None
    txt = txt.replace("₹", "").replace("INR", "").replace("Rs.", "").replace("Rs", "")
    txt = txt.replace(",", "")
    txt = re.sub(r"\s+", "", txt).strip()
    m = re.search(r"(-?\d+(?:\.\d+)?)", txt)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None


def normalize_amount_to_crores(amount: Optional[float]) -> Optional[float]:
    """
    Normalize amounts to crores. 
    If amount appears to be in full rupees (very large number), convert to crores.
    Threshold: amounts >= 100,000 are assumed to be in rupees and converted to crores.
    """
    if amount is None:
        return None

    # If amount is >= 100,000 (1 lakh crores, highly unlikely), assume it's in full rupees
    # 1 crore = 10,000,000 rupees
    if amount >= 100000:
        return round(amount / 10000000, 4)

    # Otherwise, assume it's already in crores
    return amount


def looks_like_pdf(fetch: FetchResult) -> bool:
    ct = (fetch.content_type or "").lower()
    return ("application/pdf" in ct) or fetch.url.lower().endswith(".pdf")


def extract_from_pdf(fetch: FetchResult, lsp_name: Optional[str] = None, rules: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    try:
        # Inline per-LSP conditional: handle Finsall specially to avoid external parser files
        try:
            page_rules = rules or {}
        except Exception:
            page_rules = {}

        if lsp_name and lsp_name.lower().startswith('finsall') or (isinstance(page_rules, dict) and page_rules.get('parser') == 'finsall_v1'):
            # Inline Finsall parsing: extract first page table and normalize rows
            import io as _io
            with pdfplumber.open(_io.BytesIO(fetch.body)) as _pdf:
                _page = _pdf.pages[0]
                _text = _page.extract_text() or ''
                _date_m = re.search(r'Date of data as on ([0-9]{1,2}(?:st|nd|rd|th)? [A-Za-z]+,? ?[0-9]{4})', _text, flags=re.I)
                _as_on_str = _date_m.group(1) if _date_m else None
                _as_on = parse_date_any(_as_on_str) if _as_on_str else None
                _tables = _page.extract_tables() or []
                if not _tables:
                    return []
                _tbl = _tables[0]
                out_rows: List[Dict[str, Any]] = []
                for _row in _tbl:
                    if not any(_cell for _cell in _row):
                        continue
                    _first = (_row[0] or '').strip() if _row[0] else ''
                    _lender = (_row[1] or '').strip() if len(_row) > 1 and _row[1] else ''
                    _amount_raw = _row[5] if len(_row) > 5 else None
                    _amount = None
                    if _amount_raw is not None:
                        _m = re.search(r'([0-9]+(?:\.[0-9]+)?)', str(_amount_raw).replace(',', ''))
                        if _m:
                            try:
                                _amount = float(_m.group(1))
                            except Exception:
                                _amount = None

                    # skip headers/totals
                    if _first.lower().startswith('sl') or (_lender and _lender.lower() == 'lender') or _first.upper() == 'TOTAL' or _first.lower().startswith('total'):
                        continue

                    if _lender and _amount is not None:
                        out_rows.append({
                            'Lender': _lender,
                            'Portfolio': None,
                            'Amount': _amount,
                            'AsOnTimestamp': _as_on,
                            'ScrapeTimestamp': None,
                        })
                        continue

                    # salvage: try neighboring cols
                    if _lender and _amount is None:
                        for _c in (3,4,5,7,8):
                            if len(_row) > _c and _row[_c]:
                                _m = re.search(r'([0-9]+(?:\.[0-9]+)?)', str(_row[_c]).replace(',', ''))
                                if _m:
                                    try:
                                        _v = float(_m.group(1))
                                        out_rows.append({'Lender': _lender, 'Portfolio': None, 'Amount': _v, 'AsOnTimestamp': _as_on, 'ScrapeTimestamp': None})
                                        break
                                    except Exception:
                                        pass
                        continue

                    if _amount is not None and not _lender:
                        # look left for lender
                        _found = None
                        for _c in range(2, -1, -1):
                            if len(_row) > _c and _row[_c]:
                                val = str(_row[_c]).strip()
                                if val and not val.isdigit():
                                    _found = val
                                    break
                        out_rows.append({'Lender': _found or None, 'Portfolio': None, 'Amount': _amount, 'AsOnTimestamp': _as_on, 'ScrapeTimestamp': None})
                return out_rows

        date_patterns = [
            # as of 1st Jan, 2025 (ordinal + month abbreviation with comma)
            r"as\s+of\s+(\d{1,2}(?:st|nd|rd|th)\s+[A-Za-z]+,?\s+\d{4})",

            # As on 31st October 25 (ordinal + 2-digit year)
            r"As\s+on\s+(\d{1,2}(?:st|nd|rd|th)\s+[A-Za-z]+\s+\d{2,4})",

            # As on November 30, 2025
            r"As\s+on\s+([A-Za-z]+ \d{1,2}, \d{4})",

            # As on 30 November 2025
            r"As\s+on\s+(\d{1,2} [A-Za-z]+ \d{4})",

            # As on 30.11.2025
            r"As\s+on\s+(\d{1,2}[./-]\d{1,2}[./-]\d{4})",

            # as on Dec'25 or as on Dec 25 (Month'YY format with "as on" prefix)
            r"as\s+on\s+([A-Za-z]{3,9}['\u2018\u2019]?\s*\d{2})",

            # Dec'25 or (Dec'25) - Month'YY format without prefix (matches Unicode quotes)
            r"([A-Za-z]{3,9}['\u2018\u2019]\d{2})\b",
        ]

        rows: List[Dict[str, Any]] = []
        last_valid_header = None  # Track header across pages for multi-page tables
        ason_text_global = ""  # Track date across all pages (usually on page 1 only)

        with pdfplumber.open(io.BytesIO(fetch.body)) as pdf:
            for page in pdf.pages:
                ason_text = ""
                text = page.extract_text() or ""

                for pattern in date_patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        ason_text = match.group(1)
                        # Save the first found date to use across all pages
                        if not ason_text_global:
                            ason_text_global = ason_text
                        break

                # Use the globally found date if current page doesn't have one
                if not ason_text and ason_text_global:
                    ason_text = ason_text_global

                tables = page.extract_tables() or []
                if not tables:
                    rows.extend(_extract_portfolio_rows_from_pdf_text(text, ason_text))
                    continue
                for tbl in tables:
                    if not tbl or len(tbl) < 2:
                        continue

                    # Check if first row looks like a header or data
                    first_row = [str(x).strip() if x else "" for x in tbl[0]]
                    is_continuation_page = False

                    # Detect continuation pages: first row contains "Portfolio" pattern (data, not header)
                    if first_row and last_valid_header:
                        first_cell = first_row[0]
                        if len(first_row) == 1:
                            # Single-col tables: merged cells like "Portfolio 6.2 -", "23\nPortfolio 8.10"
                            if re.search(r'Portfolio\s+\d+\.\d+', first_cell, re.IGNORECASE):
                                is_continuation_page = True
                        else:
                            # Multi-col tables: first cell is a portfolio identifier like "Portfolio 3.9"
                            # (not a generic header like "Portfolio")
                            if re.search(r'^Portfolio\s+\d+[\.\d]*\s*$', first_cell, re.IGNORECASE):
                                is_continuation_page = True

                    if is_continuation_page and last_valid_header:
                        # Use header from previous page and process ALL rows as data
                        header = last_valid_header
                        data_rows = tbl  # Include first row as data
                    else:
                        # Normal table with header in first row
                        header = first_row

                        # If headers have duplicates or empties, use col_0, col_1, col_2 instead
                        if len(header) != len(set(h for h in header if h)) or any(not h for h in header):
                            header = [f"col_{i}" for i in range(len(header))]
                        else:
                            # Save this as a valid header for potential continuation pages
                            last_valid_header = header

                        data_rows = tbl[1:]  # Skip header row

                    for r in data_rows:
                        vals = [str(x).strip() if x else "" for x in r]
                        if not any(v.strip() for v in vals):
                            continue

                        # Check if any cell contains newlines with multiple data entries
                        # If so, split into multiple rows (e.g., Bhanix PDF with merged data)
                        split_rows = []
                        has_multiline = False
                        multiline_col_idx = -1

                        for idx, val in enumerate(vals):
                            if '\n' in val and len([line for line in val.split('\n') if line.strip()]) > 1:
                                # Found a cell with multiple non-empty lines
                                has_multiline = True
                                multiline_col_idx = idx
                                break

                        if has_multiline and multiline_col_idx >= 0:
                            # Split the multiline cell into separate rows
                            lines = [line.strip() for line in vals[multiline_col_idx].split('\n') if line.strip()]
                            # Filter out "Total" lines as they are summary rows
                            lines = [line for line in lines if
                                     not re.match(r'^Total\s*\d*\.?\d*$', line, re.IGNORECASE)]

                            for line in lines:
                                # Create a new row for each line
                                new_vals = vals.copy()
                                new_vals[multiline_col_idx] = line
                                row = {header[i] if i < len(header) else f"col_{i}": new_vals[i] for i in
                                       range(len(new_vals))}
                                row['ason'] = parse_date_any(ason_text)
                                rows.append(row)
                        else:
                            # Normal single-line row
                            row = {header[i] if i < len(header) else f"col_{i}": vals[i] for i in range(len(vals))}
                            row['ason'] = parse_date_any(ason_text)
                            rows.append(row)
        return rows
    except Exception as exc:
        raise RuntimeError(f"Failed to extract data from PDF: {exc}")


def _extract_portfolio_rows_from_pdf_text(text: str, ason_text: str) -> List[Dict[str, Any]]:
    """
    Fallback parser for PDF disclosures where tables are rendered as plain text lines
    (e.g., FinAGG). Detects lines that start with "Portfolio" and captures amount/FLDG.
    """
    if not text:
        return []

    # Check if this is FinAGG format
    if "FinAGG" in text or "Portfolio OS as on" in text:
        # Use dedicated FinAGG parser  
        scrape_ts = dt.datetime.now(tz=dt.timezone.utc)
        return parse_finagg_dlg_plain_text(text, "FinAGG Services Private Limited", scrape_ts)

    rows: List[Dict[str, Any]] = []
    ason_dt = parse_date_any(ason_text)
    pattern = re.compile(r"^(portfolio\s*\d+)\s+([0-9,\s]+?)(?:\s+(yes|no))?\s*$", re.IGNORECASE)

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Normalize whitespace and fix OCR quirks like "Portfoliol" (Portfolio 1)
        line = re.sub(r"(?i)portfoliol", "Portfolio 1", line, count=1)
        line = re.sub(r"(?i)portfolioi(?![a-z])", "Portfolio 1", line, count=1)
        line = re.sub(r"(?i)(portfolio)(\d)", r"\1 \2", line)
        line = re.sub(r"\s+", " ", line)

        match = pattern.match(line)
        if not match:
            continue

        portfolio_label = " ".join(match.group(1).split())
        amount_chunk = match.group(2).replace(" ", "")
        amount_clean = re.sub(r"[^0-9.,]", "", amount_chunk)
        if not amount_clean:
            continue

        fldg_flag = match.group(3)
        rows.append({
            "Regulated Entity (Lender)": portfolio_label,
            "Portfolio OS as on 31-12-2025": amount_clean,
            "FLDG": fldg_flag.title() if fldg_flag else None,
            'ason': ason_dt
        })

    return rows


# noinspection PyArgumentList
def extract_from_html_tables(fetch: FetchResult, table_index: Optional[int] = None) -> List[Dict[str, Any]]:
    try:
        soup = BeautifulSoup(fetch.body, "html.parser")
        tables = soup.find_all("table")

        # If table_index is specified, extract only from that table
        if table_index is not None:
            try:
                tables = [tables[table_index]]
            except IndexError:
                return []

        rows: List[Dict[str, Any]] = []
        for t in tables:
            # Check for thead with th elements (not wrapped in tr)
            thead = t.find("thead")
            headers = None

            if thead:
                # Headers in thead (may or may not be in a tr)
                # Check for both th and td elements (some tables use td with bold text for headers)
                th_elements = thead.find_all(["th", "td"])
                if th_elements:
                    headers = [th.get_text(separator=" ", strip=True) for th in th_elements]

            # Get data rows from tbody or all tr elements
            tbody = t.find("tbody")
            trs = tbody.find_all("tr") if tbody else t.find_all("tr")

            if len(trs) < 1:
                continue

            # Drop leading caption rows that span the entire table (common in RBI disclosure blocks)
            while trs:
                first_cells = trs[0].find_all(["td", "th"])
                if len(first_cells) == 0:
                    trs = trs[1:]
                    continue
                if len(first_cells) != 1:
                    break
                first_cell = first_cells[0]
                colspan = int(first_cell.get("colspan", 1) or 1)
                has_th = len(trs[0].find_all("th")) > 0
                text = first_cell.get_text(separator=" ", strip=True)
                if colspan > 1 and not has_th and text:
                    trs = trs[1:]
                    continue
                break

            if len(trs) < 1:
                continue

            # If no headers from thead, try to detect from first tr
            if not headers:
                first_row_cells = trs[0].find_all(["th", "td"])
                potential_headers = [c.get_text(separator=" ", strip=True) for c in first_row_cells]

                # Check if first row is actually a header (has th tags or non-numeric content)
                has_th = len(trs[0].find_all("th")) > 0
                # UniOrbit has a header row with all <td>s, so we need a more robust check
                # that also accounts for currency symbols.
                is_header_row = has_th or (potential_headers and not all(
                    h.replace('.', '').replace(',', '').replace('-', '').replace('₹', '').strip().isdigit() for h in
                    potential_headers if h.strip()))

                if is_header_row and any(potential_headers):
                    headers = potential_headers
                    trs = trs[1:]  # Skip the header row

            # If still no headers, use column indices
            if not headers:
                num_cols = len(trs[0].find_all(["td", "th"])) if trs else 0
                headers = [f"col_{i}" for i in range(num_cols)]

            span_buffers = [None] * len(headers)

            # Extract data rows
            for tr in trs:
                cells = tr.find_all(["td", "th"])
                if not cells:
                    continue
                if len(cells) == 1:
                    span = int(cells[0].get("colspan", 1) or 1)
                    text = cells[0].get_text(separator=" ", strip=True)
                    if span >= len(headers) and text:
                        continue
                cell_iter = iter(cells)
                vals: List[str] = []
                col_idx = 0

                while col_idx < len(headers):
                    span_entry = span_buffers[col_idx]
                    if span_entry:
                        text, remaining = span_entry
                        vals.append(text)
                        remaining -= 1
                        span_buffers[col_idx] = (text, remaining) if remaining > 0 else None
                        col_idx += 1
                        continue

                    try:
                        cell = next(cell_iter)
                    except StopIteration:
                        vals.append("")
                        col_idx += 1
                        continue

                    text = cell.get_text(separator=" ", strip=True)
                    colspan = int(cell.get("colspan", 1) or 1)
                    rowspan = int(cell.get("rowspan", 1) or 1)

                    for offset in range(colspan):
                        target_col = col_idx + offset
                        if target_col >= len(headers):
                            break
                        vals.append(text)
                        if rowspan > 1:
                            span_buffers[target_col] = (text, rowspan - 1)
                    col_idx += colspan

                if not any(v.strip() for v in vals):
                    continue

                row_dict = {
                    headers[i] if i < len(headers) else f"col_{i}": vals[i] if i < len(vals) else ""
                    for i in range(len(headers))
                }
                rows.append(row_dict)
        return rows
    except Exception as exc:
        raise RuntimeError(f"Failed to extract data from HTML tables: {exc}")


def render_url_to_pdf(url: str,
                      timeout_ms: int = 60_000,
                      wait_ms: int = 0,
                      wait_until: str = "networkidle",
                      pre_click_js: Optional[str] = None,
                      ) -> FetchResult:
    from DatabaseOperation.DatabaseModels.master_models import FetchResult
    if not PLAYWRIGHT_AVAILABLE:
        raise RuntimeError("Playwright not installed/available. Install playwright to enable HTML->PDF rendering.")
    from playwright.sync_api import TimeoutError as PWTimeout
    try:
        with sync_playwright() as context_manager:
            browser = context_manager.chromium.launch(headless=True,
                                                      args=["--disable-blink-features=AutomationControlled"])
            context = browser.new_context(user_agent=BROWSER_USER_AGENT, extra_http_headers=BROWSER_HEADERS)
            page = context.new_page()
            wait_mode = wait_until if wait_until in {"load", "domcontentloaded", "networkidle"} else "networkidle"
            try:
                page.goto(url, wait_until=wait_mode, timeout=timeout_ms)
            except Exception as e:
                # Retry with a more permissive strategy if initial navigation times out
                try:
                    if isinstance(e, PWTimeout) or 'Timeout' in str(e):
                        # retry once using 'load' and a longer timeout
                        page.goto(url, wait_until='load', timeout=max(timeout_ms * 2, 120000))
                    else:
                        raise
                except Exception:
                    context.close()
                    browser.close()
                    raise

            if pre_click_js:
                page.evaluate(pre_click_js)
                page.wait_for_timeout(2000)
            if wait_ms:
                page.wait_for_timeout(wait_ms)
            pdf_bytes = page.pdf(format="A4", print_background=True, prefer_css_page_size=True)
            context.close()
            browser.close()
            return FetchResult(
                url=url,
                status_code=200,
                content_type="application/pdf",
                body=pdf_bytes,
                fetch_mode_used="playwright-pdf",
            )
    except Exception as ex:
        raise RuntimeError(f"Failed to render URL to PDF: {ex}")


def extract_dlg_from_plain_text(
        html: bytes,
        lsp_name: str,
        scrape_ts: Optional[dt.datetime] = None,
        rules_json: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Extract DLG disclosures from a page where data is in plain text (not HTML tables).

    Output schema:
      LSP Name, Lender, Portfolio, Amount, AsOnTimestamp, ScrapeTimestamp
    """
    try:
        if scrape_ts is None:
            scrape_ts = dt.datetime.now(tz=dt.timezone.utc)

        text = _clean_html_to_text(html)

        # Check for FinAGG-specific format first
        if "FinAGG" in lsp_name or "Portfolio OS as on" in text:
            return parse_finagg_dlg_plain_text(text, lsp_name, scrape_ts)

        # Check for Finnable-specific format (alternating portfolio number and amount lines)
        if "Finnable" in lsp_name or ("Portfolio Number" in text and "Disbursement" in text):
            return parse_finnable_dlg_plain_text(text, lsp_name, scrape_ts)

        # Check if rules specify regex-based extraction
        if rules_json:
            try:
                rules = json.loads(rules_json) if isinstance(rules_json, str) else rules_json
                field_map = rules.get("field_map", {})

                # Check if all fields use regex (regex-based extraction mode)
                uses_regex = all(
                    isinstance(field_map.get(f), dict) and "regex" in field_map.get(f, {})
                    for f in ["lender", "portfolio", "amount"]
                    if f in field_map
                )

                if uses_regex:
                    return extract_from_regex_patterns(text, lsp_name, scrape_ts, rules)
            except Exception:
                pass  # Fall through to CRED-style parsing

        """
        This works for cred. Can include more such cases on need basis with conditions
        """
        rows = parse_cred_style_dlg_plain_text(text)

        return rows
    except Exception as ex:
        raise RuntimeError(f"Error extracting DLG from plain text: {ex}")


def extract_finsall_grand_total(
        fetch: FetchResult,
        lsp_name: str,
        scrape_ts: dt.datetime,
        rules: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Extract single grand-total row from Finsall's plain text disclosure."""
    text = _clean_html_to_text(fetch.body)
    match = re.search(
        r"total of\s+(\d+)\s+portfolios.*?amounting to\s+INR\s+([0-9.,]+)\s*Cr[\"']?",
        text,
        re.IGNORECASE | re.DOTALL
    )
    if not match:
        return []

    portfolio_count = match.group(1)
    amount_str = match.group(2).replace(',', '')
    try:
        amount = float(amount_str)
    except ValueError:
        return []

    as_on_cfg = rules.get("field_map", {}).get("as_on") if rules else None
    as_on_dt = None
    if isinstance(as_on_cfg, dict):
        # Try constant first
        if "constant" in as_on_cfg:
            as_on_dt = parse_date_any(as_on_cfg["constant"])
        # Fallback disabled - if no date found, leave as None
        # elif "fallback" in as_on_cfg:
        #     fallback_type = as_on_cfg["fallback"]
        #     if fallback_type == "previous_month_end":
        #         as_on_dt = calculate_previous_month_end(scrape_ts)
        #     elif fallback_type == "previous_quarter_end":
        #         as_on_dt = calculate_previous_quarter_end(scrape_ts)
    elif isinstance(as_on_cfg, str):
        as_on_dt = parse_date_any(as_on_cfg)

    return [{
        "LSP Name": lsp_name,
        "Lender": None,
        "Portfolio": f"Grand Total ({portfolio_count} portfolios)",
        "Amount": amount,
        "AsOnTimestamp": as_on_dt,
        "ScrapeTimestamp": scrape_ts,
        "_force_include": True,
    }]


def extract_from_regex_patterns(
        text: str,
        lsp_name: str,
        scrape_ts: dt.datetime,
        rules: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Extract DLG data using regex patterns from rules.
    
    Scans text line by line to find lenders, then portfolios under each lender.
    """
    field_map = rules.get("field_map", {})
    as_on_config = field_map.get("as_on", {})

    # Get regex patterns
    lender_pattern = field_map.get("lender", {}).get("regex")
    portfolio_pattern = field_map.get("portfolio", {}).get("regex")
    amount_pattern = field_map.get("amount", {}).get("regex")

    if not all([lender_pattern, portfolio_pattern, amount_pattern]):
        return []

    # Parse date with support for regex, constant, fallback
    as_on_date = None
    if isinstance(as_on_config, dict):
        # Try regex extraction first
        if "regex" in as_on_config:
            as_on_regex = as_on_config["regex"]
            match = re.search(as_on_regex, text, re.IGNORECASE)
            if match:
                date_str = match.group(1).strip()
                as_on_date = parse_date_any(date_str)

        # Try constant (backward compatibility)
        if not as_on_date and "constant" in as_on_config:
            try:
                as_on_date = dateparser.parse(as_on_config["constant"])
            except Exception:
                pass

        # Fallback disabled - if no date found, leave as None
        # if not as_on_date and "fallback" in as_on_config:
        #     fallback_type = as_on_config["fallback"]
        #     if fallback_type == "previous_month_end":
        #         as_on_date = calculate_previous_month_end(scrape_ts)
        #     elif fallback_type == "previous_quarter_end":
        #         as_on_date = calculate_previous_quarter_end(scrape_ts)

    lines = text.splitlines()
    current_lender = None
    rows = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Try to match lender
        lender_match = re.search(lender_pattern, line, re.IGNORECASE)
        if lender_match:
            current_lender = lender_match.group(1).strip()
            continue

        # Try to match portfolio and amount
        portfolio_match = re.search(portfolio_pattern, line, re.IGNORECASE)
        amount_match = re.search(amount_pattern, line, re.IGNORECASE)

        if portfolio_match and amount_match:
            portfolio = portfolio_match.group(1).strip()
            amount_str = amount_match.group(1).strip()

            try:
                amount = float(amount_str.replace(',', ''))
            except:
                continue

            rows.append({
                "LSP Name": lsp_name,
                "Lender": current_lender,
                "Portfolio": portfolio,
                "Amount": amount,
                "AsOnTimestamp": as_on_date,
                "ScrapeTimestamp": scrape_ts
            })

    return rows


def parse_cred_style_dlg_plain_text(
        text: str
) -> List[Dict[str, Any]]:
    """
    Parse DLG plain-text disclosures formatted like:

      Digital Lending App: CRED
      ... as on November 30, 2025 ...
      Lender A (in INR crore):
      Portfolio A1: 100.3
      ...
      Digital Lending App: Prefr / CreditVidya
      ...

    Returns rows with:
      LSP Name, Lender, Portfolio, Amount, AsOnTimestamp, ScrapeTimestamp
    """
    deduped = []
    error = ""
    scrape_ts = dt.datetime.now(tz=dt.timezone.utc)

    # Normalize newlines and spaces
    try:
        lines = [ln.strip() for ln in text.splitlines()]
        # Keep empty lines as separators (we rely on headings)
        # but remove repeated whitespace inside lines
        lines = [re.sub(r"\s+", " ", ln) for ln in lines]

        rows: List[Dict[str, Any]] = []

        current_lsp: Optional[str] = None
        current_lender: Optional[str] = None
        current_as_on: Optional[dt.datetime] = None

        # Patterns
        p_app = re.compile(r"^Digital Lending App:\s*(.+)$", re.IGNORECASE)
        p_as_on = re.compile(r"\bas on\b\s+(.+?)(?:\s*\(|\s*$)", re.IGNORECASE)
        p_lender = re.compile(r"^(Lender\s+[A-Za-z0-9]+)\b.*?:\s*$", re.IGNORECASE)
        p_portfolio = re.compile(
            r"^Portfolio\s+([A-Za-z0-9]+(?:\.[A-Za-z0-9]+)?)\s*:\s*([0-9]+(?:\.[0-9]+)?)\s*$",
            re.IGNORECASE
        )

        def parse_date(s: str) -> Optional[dt.datetime]:
            try:
                return dateparser.parse(s, dayfirst=True, fuzzy=True)
            except Exception:
                return None

        for ln in lines:
            if not ln:
                continue

            m_app = p_app.match(ln)
            if m_app:
                current_lsp = m_app.group(1).strip()
                current_lender = None
                current_as_on = None
                continue

            # capture as-on line anywhere under the app
            if current_lsp:
                m_ason = p_as_on.search(ln)
                # only set if line actually contains "as on"
                if m_ason and "as on" in ln.lower():
                    # Example trailing text: "November 30, 2025 (unaudited numbers):"
                    date_candidate = m_ason.group(1).strip()
                    # remove trailing qualifiers like "unaudited numbers" if present
                    date_candidate = re.sub(r"\bunaudited\b.*$", "", date_candidate, flags=re.IGNORECASE).strip(" :.-")
                    parsed = parse_date(date_candidate)
                    if parsed:
                        current_as_on = parsed
                    # do not continue; line might also contain something else, but usually not
                    continue

            m_lender = p_lender.match(ln)
            if m_lender:
                current_lender = m_lender.group(1).strip()
                continue

            m_port = p_portfolio.match(ln)
            if m_port and current_lsp:
                portfolio = m_port.group(1).strip()
                amount = float(m_port.group(2))

                rows.append({
                    "LSP Name": current_lsp,
                    "Lender": current_lender,  # allowed to be None if not found
                    "Portfolio": portfolio,
                    "Amount": amount,
                    "AsOnTimestamp": current_as_on,
                    "ScrapeTimestamp": scrape_ts
                })

        # de-dupe (safe in case the text repeats)
        seen = set()
        for r in rows:
            k = (
                r["LSP Name"],
                r["Lender"],
                r["Portfolio"],
                r["Amount"],
                r["AsOnTimestamp"].isoformat() if r["AsOnTimestamp"] else None
            )
            if k in seen:
                continue
            seen.add(k)
            deduped.append(r)
    except RuntimeError as ex:
        raise ex

    return deduped


def parse_finnable_dlg_plain_text(
        text: str,
        lsp_name: str,
        scrape_ts: dt.datetime
) -> List[Dict[str, Any]]:
    """
    Parse Finnable Credit Ltd's DLG disclosure format.
    
    The page has Portfolio Number and Disbursement columns where data alternates line-by-line:
    Portfolio Number
    1
    6,19,25,366
    2
    1,84,23,874
    ...
    Total
    ...
    Last updated as of November 2025
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Find the date
    as_on_date = None
    date_match = re.search(r"Last updated as of ([A-Za-z]+ \d{4})", text, re.IGNORECASE)
    if date_match:
        date_str = date_match.group(1).strip()
        parsed = parse_date_any(date_str)
        if parsed:
            # Month YYYY format - use last day of month
            as_on_date = parsed.replace(day=1) + dt.timedelta(days=32)
            as_on_date = as_on_date.replace(day=1) - dt.timedelta(days=1)

    rows = []
    portfolio_started = False
    i = 0

    while i < len(lines):
        line = lines[i]

        if "Portfolio Number" in line:
            portfolio_started = True
            i += 1
            continue

        if not portfolio_started:
            i += 1
            continue

        # Stop at Total or Last updated
        if line.lower().startswith("total") or "last updated" in line.lower():
            break

        # Check if line is a portfolio number (single digit)
        if re.match(r'^\d+$', line):
            portfolio_num = line
            # Next line should be the amount
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                if re.match(r'^[\d,]+$', next_line):
                    # Remove commas and convert to float
                    amount_str = next_line.replace(',', '')
                    try:
                        amount = float(amount_str)
                        rows.append({
                            "LSP Name": lsp_name,
                            "Lender": None,
                            "Portfolio": f"Portfolio {portfolio_num}",
                            "Amount": amount,
                            "AsOnTimestamp": as_on_date,
                            "ScrapeTimestamp": scrape_ts
                        })
                    except ValueError:
                        pass
                    i += 2  # Skip both lines
                    continue

        i += 1

    return rows


def parse_finagg_dlg_plain_text(
        text: str,
        lsp_name: str,
        scrape_ts: dt.datetime
) -> List[Dict[str, Any]]:
    """
    Parse FinAGG-style DLG plain text disclosures.
    
    Text pattern from pdfplumber:
    Portfolio l 2,30,25,89,904 No  <- Portfolio 1 with amount on same line
    1,47,83,34,565                 <- standalone amount (belongs to Portfolio 2)
    Portfolio 2 No                 <- Portfolio 2 with only FLDG
    1,37,94,55,277                 <- standalone amount (belongs to Portfolio 3)
    Portfolio 3 Yes                <- Portfolio 3 with only FLDG
    ...
   
 Portfolio 11 4,75,33,000 Yes   <- Portfolio 11 with amount on same line
    1,23,72,947                    <- standalone amount (belongs to Portfolio 12)
    Portfolio 12 No                <- Portfolio 12 with only FLDG
    
    Key insight: Standalone amounts appear BEFORE the portfolio line they belong to!
    """

    rows: List[Dict[str, Any]] = []

    # Extract date first — try 'Portfolio OS as on' (old format) then plain 'as on'
    as_on_date = None
    date_match = re.search(
        r"(?:Portfolio\s+OS\s+as\s+on|as\s+on)\s+([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{4})",
        text, re.IGNORECASE
    )
    if date_match:
        date_str = date_match.group(1)
        as_on_date = parse_date_any(date_str)

    # Split into lines
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    pending_amount = None  # Amount from previous line to use with next portfolio

    for i, line in enumerate(lines):
        # Check if this is a standalone amount line (to be used with NEXT portfolio)
        if re.match(r"^[0-9,\s]+$", line) and 'Total' not in lines[i - 1] if i > 0 else True:
            clean_amount = line.replace(',', '').replace(' ', '')
            if len(clean_amount) >= 6:  # Reasonable amount size
                pending_amount = clean_amount
                continue

        # Match lines starting with "Portfolio" - handle both "Portfolio9" and "Portfolio 9"
        match = re.match(r"Portfolio\s*([0-9l]+)(?:\s+([0-9,\s]+))?\s*(?:(Yes|No))?\s*$", line, re.IGNORECASE)

        if match:
            portfolio_num = match.group(1)
            # Handle OCR artifacts
            if portfolio_num.lower() == 'l':
                portfolio_num = '1'

            amount_str = match.group(2)  # Amount on same line (if present)
            fldg = match.group(3)  # FLDG status

            # Determine the amount to use
            if amount_str:
                # Amount is on the same line
                final_amount_str = amount_str
                pending_amount = None  # Don't use pending since we have one here
            elif pending_amount:
                # Use the pending amount from previous line
                final_amount_str = pending_amount
                pending_amount = None
            else:
                # No amount available, skip this portfolio
                continue

            try:
                # Clean and parse amount
                clean_amount = final_amount_str.replace(',', '').replace(' ', '')
                amount = float(clean_amount)

                # Skip the Total row
                if 'total' in portfolio_num.lower() or amount > 7000000000:  # Total is usually very large
                    continue

                rows.append({
                    "LSP Name": lsp_name,
                    "Lender": None,
                    "Portfolio": f"Portfolio {portfolio_num}",
                    "Amount": amount,
                    "AsOnTimestamp": as_on_date,
                    "ScrapeTimestamp": scrape_ts
                })
            except ValueError:
                pass  # Skip if amount can't be parsed

        elif line.lower().startswith('portfolio'):
            # Fallback: pdfplumber merged the portfolio number into the amount with no space
            # e.g. "Portfolio 19,88,31,33,840 No" → Portfolio 1, amount 19,88,31,33,840
            merged = re.match(r"Portfolio\s+(\d[\d,]+)\s+(Yes|No)\s*$", line, re.IGNORECASE)
            if merged:
                amount_raw = merged.group(1).replace(',', '').replace(' ', '')
                try:
                    amount = float(amount_raw)
                    inferred_num = str(len(rows) + 1)
                    rows.append({
                        "LSP Name": lsp_name,
                        "Lender": None,
                        "Portfolio": f"Portfolio {inferred_num}",
                        "Amount": amount,
                        "AsOnTimestamp": as_on_date,
                        "ScrapeTimestamp": scrape_ts
                    })
                except ValueError:
                    pass

    return rows


# -----------------------------
# RULE-DRIVEN NORMALIZATION
# -----------------------------


def load_rules(rules_json: Optional[object]) -> Dict[str, Any]:
    """Accept either a JSON string or an already-parsed mapping and return a dict.

    Returns empty dict on None or parse error.
    """
    if not rules_json:
        return {}
    # If already a mapping/dict, return as-is
    if isinstance(rules_json, dict):
        return rules_json
    try:
        return json.loads(rules_json)
    except Exception:
        return {}


def pick_by_keys(rr: Dict[str, Any], keys: List[str]) -> Optional[str]:
    def normalize_for_matching(text: str) -> str:
        """Normalize text for field matching by replacing special chars that may have encoding issues."""
        # Replace rupee symbol and other currency symbols that might become ? in PostgreSQL
        return text.replace('₹', '?').replace('₨', '?').replace('₹', '?')

    # First try exact match
    for k in keys:
        if k in rr and rr[k] is not None and str(rr[k]).strip():
            return str(rr[k]).strip()

    # Then try normalized matching (handles encoding issues like ₹ -> ?)
    for col, v in rr.items():
        normalized_col = normalize_for_matching(str(col).lower())
        for k in keys:
            normalized_key = normalize_for_matching(str(k).lower())
            if normalized_key in normalized_col:
                if v is not None and str(v).strip():
                    return str(v).strip()

    # Finally try original substring matching as fallback
    for col, v in rr.items():
        lcol = str(col).lower()
        for k in keys:
            if str(k).lower() in lcol:
                if v is not None and str(v).strip():
                    return str(v).strip()
    return None


def extract_by_regex(text: str, pattern: str, group: int = 1) -> Optional[str]:
    if not text or not pattern:
        return None

    # Only normalize text for currency symbol encoding issues (₹ -> ?)
    # Don't touch the pattern - let it be used as-is
    def normalize_currency_in_text(s: str) -> str:
        return s.replace('₹', '?').replace('₨', '?')

    normalized_text = normalize_currency_in_text(text)

    m = re.search(pattern, normalized_text, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    try:
        return m.group(group).strip()
    except Exception:
        return None


# noinspection PyArgumentList
def page_level_values(fetch: FetchResult, rules: Dict[str, Any]) -> Dict[str, Any]:
    try:
        out: Dict[str, Any] = {}
        page_rules = rules.get("page_level") or {}
        table_index = rules.get("table_index")

        body_text = ""
        if not looks_like_pdf(fetch):
            try:
                soup = BeautifulSoup(fetch.body, "html.parser")
                # noinspection PyArgumentList
                body_text = soup.get_text(" ", strip=True)
            except Exception:
                body_text = ""

        if "as_on_constant" in page_rules:
            out["as_on"] = page_rules["as_on_constant"]

        if "lender_constant" in page_rules:
            out["lender"] = page_rules["lender_constant"]

        lender_regex = page_rules.get("lender_regex")
        if lender_regex and body_text:
            try:
                soup = BeautifulSoup(fetch.body, "html.parser")
                body_text = soup.get_text("\n", strip=True)
            except Exception:
                body_text = ""
            grp = int(page_rules.get("lender_group", 1))
            v = extract_by_regex(body_text, lender_regex, group=grp)
            if v:
                out["lender"] = v

        as_on_regex = page_rules.get("as_on_regex")
        if as_on_regex and body_text:
            grp = int(page_rules.get("as_on_group", 1))
            # If table_index is specified, find all matches and select the one at that index
            if table_index is not None:
                try:
                    matches = re.findall(as_on_regex, body_text, flags=re.IGNORECASE | re.DOTALL)
                    if matches:
                        # Handle both single groups and tuple groups from regex
                        if isinstance(matches[table_index], tuple):
                            out["as_on"] = matches[table_index][grp - 1].strip()
                        else:
                            out["as_on"] = matches[table_index].strip()
                except (IndexError, Exception):
                    pass
            else:
                v = extract_by_regex(body_text, as_on_regex, group=grp)
                if v:
                    out["as_on"] = v

        return out
    except Exception as ex:
        raise RuntimeError(f"Error extracting page-level values: {ex}")


def normalize_rows(
        raw_rows: List[Dict[str, Any]],
        fetch: FetchResult,
        lsp_name: str,
        scrape_ts: dt.datetime,
        rules_json: Optional[str]
) -> Tuple[CrawlStatus, List[Dict[str, Any]], str]:
    from DatabaseOperation.DatabaseModels.master_models import CrawlStatus
    rules = load_rules(rules_json)
    field_map = rules.get("field_map") or {}
    page_vals = page_level_values(fetch, rules)

    defaults = {
        "lender": ["Lender", "Lending Partner", "Partner", "NBFC", "Bank"],
        "portfolio": ["Portfolio", "DLG set", "Cohort", "Set", "Portfolio Name"],
        "amount": ["Amount", "Outstanding AUM", "AUM", "Outstanding", "DLG Amount", "Outstanding AUM (₹ crores)",
                   "Outstanding AUM (INR crore)"],
        "as_on": ["ason", "As on", "As-on", "AsOn", "As on date", "Date", "AsOnTimestamp"],
    }

    def get_field(raw_row: Dict[str, Any], fname: str) -> Optional[str]:
        spec = field_map.get(fname)

        # Handle simple string mapping like "portfolio": "Portfolio"
        if isinstance(spec, str):
            return pick_by_keys(raw_row, [spec])

        # Handle dict-based spec
        if not isinstance(spec, dict):
            spec = {}

        # Handle constant value
        if "constant" in spec and spec["constant"] is not None:
            return str(spec["constant"]).strip()

        # Handle regex-based column matching (when regex is meant to find the COLUMN, not extract from value)
        # This is the case when we have {"regex": "..."} without "keys"
        if "regex" in spec and "keys" not in spec and fname != "as_on":
            regex_pattern = spec["regex"]
            for col_name, col_value in raw_row.items():
                if re.search(regex_pattern, str(col_name), flags=re.IGNORECASE):
                    # Found the column, return its value
                    if col_value is not None and str(col_value).strip():
                        return str(col_value).strip()
            return None

        # Handle dynamic date extraction for as_on field
        # Only process if spec has actual configuration (not just an empty dict)
        if fname == "as_on" and isinstance(spec, dict) and spec:
            extracted_date = None

            # Try to extract date from column names (not values)
            if "extract_regex" in spec:
                extract_from = spec.get("extract_from", "amount_column")
                date_format = spec.get("date_format", None)

                # Determine which column name to extract from
                source_column_name = None
                if extract_from == "amount_column":
                    # Get the amount field spec to find the column name
                    amount_spec = field_map.get("amount")
                    if isinstance(amount_spec, str):
                        source_column_name = amount_spec
                    elif isinstance(amount_spec, dict):
                        # If amount spec has a regex (for column matching), use it
                        if "regex" in amount_spec and "keys" not in amount_spec:
                            regex_pattern = amount_spec["regex"]
                            for col_name in raw_row.keys():
                                if re.search(regex_pattern, str(col_name), flags=re.IGNORECASE):
                                    source_column_name = col_name
                                    break
                        else:
                            # Try to find matching column in raw_row using keys
                            keys = amount_spec.get("keys") or defaults.get("amount", [])
                            for col_name in raw_row.keys():
                                for key in keys:
                                    if str(key).lower() in str(col_name).lower():
                                        source_column_name = col_name
                                        break
                                if source_column_name:
                                    break

                elif extract_from == "portfolio_column":
                    # Get the portfolio field spec to find the column name
                    portfolio_spec = field_map.get("portfolio")
                    if isinstance(portfolio_spec, str):
                        source_column_name = portfolio_spec
                    elif isinstance(portfolio_spec, dict):
                        # If portfolio spec has a regex (for column matching), use it
                        if "regex" in portfolio_spec and "keys" not in portfolio_spec:
                            regex_pattern = portfolio_spec["regex"]
                            for col_name in raw_row.keys():
                                if re.search(regex_pattern, str(col_name), flags=re.IGNORECASE):
                                    source_column_name = col_name
                                    break
                        else:
                            # Try to find matching column in raw_row using keys
                            keys = portfolio_spec.get("keys") or defaults.get("portfolio", [])
                            for col_name in raw_row.keys():
                                for key in keys:
                                    if str(key).lower() in str(col_name).lower():
                                        source_column_name = col_name
                                        break
                                if source_column_name:
                                    break

                # Try to extract date from the column name using regex
                if source_column_name:
                    extracted = extract_by_regex(source_column_name, spec["extract_regex"], group=1)
                    if extracted:
                        # Parse with format hint if provided
                        if date_format:
                            parsed_date = parse_date_with_format(extracted, date_format)
                            if parsed_date:
                                extracted_date = parsed_date.strftime("%Y-%m-%d")
                        else:
                            # Try general parsing
                            parsed_date = parse_date_any(extracted)
                            if parsed_date:
                                extracted_date = parsed_date.strftime("%Y-%m-%d")

            # Handle extract_from_button for SaveIN (button text contains date)
            if not extracted_date and spec.get("extract_from_button"):
                # This would be handled by the playwright pre-click logic
                # The button text might be in page_vals or we fall back
                pass

            # If extraction succeeded, return it
            if extracted_date:
                return extracted_date

            # If no explicit extraction method worked, try standard field extraction first
            # (this picks up dates from PDF 'ason' field, HTML date columns, etc.)
            if not extracted_date:
                keys = spec.get("keys") or defaults[fname]
                standard_val = pick_by_keys(raw_row, keys)
                if standard_val:
                    return standard_val

            # Fallback disabled - if no date found, return None instead of calculating fallback
            # This ensures data accuracy - only actual dates from pages are used
            # if "fallback" in spec:
            #     fallback_type = spec["fallback"]
            #     if fallback_type == "previous_month_end":
            #         fallback_date = calculate_previous_month_end(scrape_ts)
            #         return fallback_date.strftime("%Y-%m-%d")
            #     elif fallback_type == "previous_quarter_end":
            #         fallback_date = calculate_previous_quarter_end(scrape_ts)
            #         return fallback_date.strftime("%Y-%m-%d")

            # If we processed as_on but found nothing, return None (don't fall through to standard extraction)
            return None

        # Standard field extraction
        keys = spec.get("keys") or defaults[fname]
        val = pick_by_keys(raw_row, keys)
        if val and spec.get("regex"):
            grp = int(spec.get("group", 1))
            val2 = extract_by_regex(val, spec["regex"], group=grp)
            # For amount field, if regex is specified but doesn't match, return None
            # This prevents extracting wrong numbers from text like "Portfolio 1.1\n-"
            # Only apply this when regex is explicitly specified for amount
            if fname == "amount" and not val2:
                return None
            return val2 if val2 else val
        return val

    out_rows: List[Dict[str, Any]] = []
    partial = False
    final_data: List[Dict[str, Any]] = []

    if not raw_rows:
        return CrawlStatus.NO_DATA, final_data, "No rows extracted from page"

    if not len(raw_rows) > 0:
        return CrawlStatus.NO_DATA, final_data, "No rows extracted from page"

    try:
        for rr in raw_rows:
            # Check if row is already normalized (has capital-case keys from plain_text parsers)
            # Plain text parsers like extract_from_regex_patterns and parse_cred_style_dlg_plain_text
            # return pre-normalized rows with keys: LSP Name, Lender, Portfolio, Amount, AsOnTimestamp, ScrapeTimestamp
            force_include = False
            if "Amount" in rr and "Portfolio" in rr:
                # Row is already normalized, but still need to normalize amount to crores
                lender_clean = rr.get("Lender")
                portfolio_clean = rr.get("Portfolio")
                # Apply amount normalization to pre-normalized rows too
                normalized_amount = normalize_amount_to_crores(rr.get("Amount"))
                # Defensively parse ason: the inline per-LSP parsers may return a string or datetime
                _ason_raw = rr.get("AsOnTimestamp")
                ason = _ason_raw if isinstance(_ason_raw, dt.datetime) else parse_date_any(_ason_raw)
                force_include = bool(rr.get("_force_include"))
            else:
                # Row needs normalization
                lender_txt = get_field(rr, "lender") or page_vals.get("lender")
                portfolio_txt = get_field(rr, "portfolio") or page_vals.get("portfolio")
                amount_txt = get_field(rr, "amount") or page_vals.get("amount")
                ason_txt = get_field(rr, "as_on") or page_vals.get("as_on")

                # Parse and normalize amount to crores
                parsed_amount = parse_amount_any(amount_txt)
                normalized_amount = normalize_amount_to_crores(parsed_amount)

                # Override LSP Name with the one from configuration (handles cases like CreditVidya on prefr.com)
                # This ensures the data is saved under the correct company name from lsp_sources_latest.csv

                # Clean up lender/portfolio: convert None to actual None, not string "None"
                lender_clean = None
                if lender_txt is not None:
                    lender_str = str(lender_txt).strip()
                    if lender_str and lender_str != "None":
                        lender_clean = lender_str

                portfolio_clean = None
                if portfolio_txt is not None:
                    portfolio_str = str(portfolio_txt).strip()
                    # Treat dash/placeholder values (-, --, –) as empty/None
                    if portfolio_str and portfolio_str != "None" and not re.fullmatch(r'[-–—]{1,3}', portfolio_str):
                        portfolio_clean = portfolio_str

                ason = parse_date_any(ason_txt)

            # Detect explicit total rows from raw data (e.g., columns labelled "Grand Total")
            raw_is_total = any(
                isinstance(val, str) and re.search(r"\btotal\b", val, flags=re.IGNORECASE)
                for val in rr.values()
            )

            row = {
                "LSP Name": lsp_name,
                "Lender": lender_clean,
                "Portfolio": portfolio_clean,
                "Amount": normalized_amount,
                "AsOnTimestamp": ason,
                "ScrapeTimestamp": scrape_ts,
            }

            if force_include:
                row["_force_include"] = True

            if raw_is_total and not force_include:
                continue

            # Skip rows where we have all None except date/scrape timestamp
            if row["Lender"] is None and row["Portfolio"] is None and row["Amount"] is None:
                continue

            # Skip rows where we have amount but no portfolio (likely bad extraction from CIN or other non-table text)
            if row["Portfolio"] is None and row["Amount"] is not None and row["Lender"] is None:
                continue

            out_rows.append(row)

        # de-dupe
        seen = set()
        deduped = []
        partial = False
        for r in out_rows:
            k = (
                r["LSP Name"],
                r["Lender"],
                r["Portfolio"],
                r["Amount"],
                r["AsOnTimestamp"].isoformat() if r["AsOnTimestamp"] else None
            )
            if k in seen:
                continue
            seen.add(k)
            deduped.append(r)

        final_data = merge_partial_rows(deduped)

        # Apply forward fill if specified in rules
        forward_fill_cols = rules.get("forward_fill") or []
        if forward_fill_cols:
            final_data = forward_fill_columns(final_data, forward_fill_cols)
    except Exception as ex:
        error = str(ex)
        return CrawlStatus.ERROR, final_data, error

    for r in final_data:
        if r["Portfolio"] is None or r["Amount"] is None:
            return CrawlStatus.PARTIAL, final_data, "Missing portfolio or amount in some rows"
        if r["AsOnTimestamp"] is None:
            return CrawlStatus.STALE, final_data, "Missing as-on date in some rows - data may be stale"
    return CrawlStatus.COMPLETED, final_data, "All rows complete"


def is_header_row(row: Dict[str, Any]) -> bool:
    """
    Detect if a row is a header row based on common patterns.
    Returns True if the row appears to be a header.
    """
    portfolio = row.get("Portfolio")
    lender = row.get("Lender")
    amount = row.get("Amount")

    # Exact match header keywords (must be exact match, not just contain)
    exact_header_keywords = [
        "portfolio", "lender", "amount", "outstanding", "aum", "dlg",
        "name", "partner", "regulated entity", "business segment",
        "cohort", "set", "total no", "s.no", "s no", "serial", "sr",
        "particulars", "portfolio name", "lender name"
    ]

    # Check if portfolio field is exactly a header keyword
    if portfolio:
        portfolio_lower = str(portfolio).lower().strip()
        if portfolio_lower in exact_header_keywords:
            return True

    # Check if lender field is exactly a header keyword
    if lender:
        lender_lower = str(lender).lower().strip()
        if lender_lower in exact_header_keywords:
            return True

    return False


def is_total_row(row: Dict[str, Any]) -> bool:
    """
    Detect if a row is a total/grand total row.
    Returns True if the row appears to be a summary total.
    """
    portfolio = row.get("Portfolio")
    lender = row.get("Lender")

    if not portfolio:
        return False

    portfolio_lower = str(portfolio).lower().strip()

    # Common total row patterns
    total_keywords = [
        "total", "grand total", "sum", "aggregate", "overall",
        "combined", "consolidated"
    ]

    # Check if portfolio field indicates a total
    for keyword in total_keywords:
        if portfolio_lower == keyword or portfolio_lower.startswith(keyword):
            return True

    # Check lender field as well
    if lender:
        lender_lower = str(lender).lower().strip()
        for keyword in total_keywords:
            if lender_lower == keyword or lender_lower.startswith(keyword):
                return True

    # Fallback: inspect all columns for explicit total keywords (handles cases like Sr='Grand Total')
    for value in row.values():
        if isinstance(value, str):
            value_lower = value.lower().strip()
            for keyword in total_keywords:
                if keyword in value_lower:
                    return True

    return False


def merge_partial_rows(rows: List[dict[str, Any]]) -> List[dict[str, Any]]:
    """
    Filter out header rows and total rows from the data.
    Also detects grand totals where amount equals sum of other rows.
    """
    if not rows:
        return []

    # First pass: group rows by LSP and collect amounts
    lsp_amounts = {}
    for row in rows:
        lsp_name = row.get("LSP Name")
        amount = row.get("Amount")
        if lsp_name and amount is not None:
            if lsp_name not in lsp_amounts:
                lsp_amounts[lsp_name] = []
            lsp_amounts[lsp_name].append((row, amount))

    # Calculate which rows are sum totals
    sum_total_rows = set()
    for lsp_name, row_amounts in lsp_amounts.items():
        # Need at least 3 rows (2 data rows + total) for sum-total detection to be reliable.
        # Otherwise a single real row paired with a total row would both be removed.
        if len(row_amounts) <= 2:
            continue

        for i, (current_row, current_amount) in enumerate(row_amounts):
            # Calculate sum of all OTHER rows
            other_sum = sum(amt for j, (_, amt) in enumerate(row_amounts) if j != i)

            # If current amount equals sum of others (within small tolerance for floating point,
            # allowing up to 0.05 Cr to handle display-rounding differences across rows)
            if abs(current_amount - other_sum) <= 0.05:
                sum_total_rows.add(id(current_row))

    # Second pass: filter out headers, totals, and sum totals
    filtered_rows = []

    for row in rows:
        if row.get("_force_include"):
            filtered_rows.append(row)
            continue
        # Skip header rows
        if is_header_row(row):
            continue

        # Skip total rows (by keyword)
        if is_total_row(row):
            continue

        # Skip rows that are sum totals
        if id(row) in sum_total_rows:
            continue

        filtered_rows.append(row)

    for row in filtered_rows:
        row.pop("_force_include", None)

    return filtered_rows


def forward_fill_column(rows: List[Dict[str, Any]], column_name: str) -> List[Dict[str, Any]]:
    """
    Forward fill missing/None values in a column with the last seen non-None value.
    
    This is useful when data like Lender is only mentioned once at the top and 
    subsequent rows under the same lender leave it blank/None.
    
    Example:
        Input:  [{"Lender": "A", "Portfolio": "1"}, {"Lender": None, "Portfolio": "2"}]
        Output: [{"Lender": "A", "Portfolio": "1"}, {"Lender": "A", "Portfolio": "2"}]
    
    Args:
        rows: List of dictionaries representing data rows
        column_name: Name of the column to forward fill
        
    Returns:
        List of rows with forward-filled values (modifies in place and returns)
    """
    if not rows:
        return rows

    last_value = None

    for row in rows:
        current_value = row.get(column_name)

        # If current value is None or empty string, use last seen value
        if current_value is None or (isinstance(current_value, str) and not current_value.strip()):
            if last_value is not None:
                row[column_name] = last_value
        else:
            # Update last_value with current non-empty value
            last_value = current_value

    return rows


def forward_fill_columns(rows: List[Dict[str, Any]], column_names: List[str]) -> List[Dict[str, Any]]:
    """
    Forward fill missing/None values in multiple columns.
    
    Applies forward_fill_column to each specified column in order.
    
    Args:
        rows: List of dictionaries representing data rows
        column_names: List of column names to forward fill
        
    Returns:
        List of rows with forward-filled values
    """
    for column_name in column_names:
        rows = forward_fill_column(rows, column_name)

    return rows


# ---------------------------------------------------------------------------
# Month-based URL promotion helpers (T-2 → T-1)
# ---------------------------------------------------------------------------

def subtract_months(dtobj: dt.datetime, months: int) -> dt.datetime:
    """Return a datetime shifted back by `months` months, clamped to day 1."""
    year = dtobj.year
    month = dtobj.month - months
    while month <= 0:
        month += 12
        year -= 1
    return dt.datetime(year=year, month=month, day=1)


def parse_month_year_token(url: str) -> Optional[Tuple[int, int, str, re.Match]]:
    """Find the first month+year token in a URL.

    Returns (year, month, matched_token_str, re.Match) or None.
    Handles formats: 'May2025', 'May-2025', 'May%2025', 'Dec25', '/2025/07/'.
    """
    # 1) named-month + year (short or full), optional separator
    m = re.search(
        r'(?P<month>(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May'
        r'|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?'
        r'|Nov(?:ember)?|Dec(?:ember)?))(?P<sep>[-_%20\s]??)(?P<year>\d{2,4})',
        url, flags=re.IGNORECASE)
    if m:
        year_s = m.group('year')
        year = int(year_s) if len(year_s) == 4 else 2000 + int(year_s)
        try:
            month = dt.datetime.strptime(m.group('month')[:3].title(), '%b').month
        except Exception:
            month = None
        return year, month, m.group(0), m

    # 2) numeric year/month like /2025/07/
    m2 = re.search(r'(?P<year>20\d{2})[^0-9]{0,3}(?P<month>0?[1-9]|1[0-2])', url)
    if m2:
        return int(m2.group('year')), int(m2.group('month')), m2.group(0), m2

    # 3) short-name + 2-digit year like Dec25
    m3 = re.search(
        r'(?P<month>Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)'
        r'(?P<year>\d{2})(?:\D|$)', url, flags=re.IGNORECASE)
    if m3:
        year = 2000 + int(m3.group('year'))
        try:
            month = dt.datetime.strptime(m3.group('month')[:3].title(), '%b').month
        except Exception:
            month = None
        return year, month, m3.group(0), m3

    return None


def build_replacement_token(orig_token: str, orig_match: re.Match,
                            new_year: int, new_month: int) -> str:
    """Build a replacement month+year token that preserves the original formatting."""
    m = re.search(r'(?P<month_name>[A-Za-z]{3,9})', orig_token)
    if m:
        month_name = m.group('month_name')
        if month_name.islower():
            mn = dt.datetime(new_year, new_month, 1).strftime('%B').lower()
        elif month_name.isupper():
            mn = dt.datetime(new_year, new_month, 1).strftime('%B').upper()
        elif len(month_name) == 3:
            mn = dt.datetime(new_year, new_month, 1).strftime('%b')
        else:
            mn = dt.datetime(new_year, new_month, 1).strftime('%B')
        y_m = re.search(r'(\d{2,4})', orig_token)
        ystr = str(new_year) if (y_m and len(y_m.group(1)) == 4) else str(new_year)[2:]
        sep = orig_match.groupdict().get('sep') or ''
        return f"{mn}{sep}{ystr}"

    mnum = re.search(r'(?P<y>20\d{2})[^0-9]{0,3}(?P<m>0?[1-9]|1[0-2])', orig_token)
    if mnum:
        newtok = re.sub(r'20\d{2}', str(new_year), orig_token, count=1)
        newtok = re.sub(r'(0?[1-9]|1[0-2])', f'{new_month:02d}', newtok, count=1)
        return newtok

    return dt.datetime(new_year, new_month, 1).strftime('%b') + str(new_year)


def head_checks_pdf(url: str, timeout: int = 20) -> bool:
    """Return True if `url` resolves to a PDF (HEAD then small GET fallback)."""
    try:
        h = requests.head(url, allow_redirects=True, timeout=timeout,
                          headers={"User-Agent": BROWSER_USER_AGENT})
        ct = (h.headers.get('content-type') or '').lower()
        if h.status_code == 200 and 'application/pdf' in ct:
            return True
        g = requests.get(url, stream=True, timeout=timeout,
                         headers={"User-Agent": BROWSER_USER_AGENT},
                         allow_redirects=True)
        if g.status_code == 200:
            chunk = g.raw.read(8) if hasattr(g.raw, 'read') else g.content[:8]
            if chunk.startswith(b'%PDF-'):
                return True
    except Exception:
        pass
    return False
