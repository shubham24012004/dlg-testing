import re
import io
import json
import datetime as dt
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from typing import Any, Dict, List, Optional, Tuple
from DatabaseOperation.SQLAlchemy.DatabaseModels import FetchResult
import pdfplumber


# -----------------------------
# PARSE HELPERS
# -----------------------------

# noinspection PyArgumentList
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
    if s is None:
        return None
    txt = str(s).strip()
    if not txt:
        return None
    try:
        return dateparser.parse(txt, dayfirst=True, fuzzy=True)
    except Exception:
        return None


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
        return round(amount / 10000000, 2)
    
    # Otherwise, assume it's already in crores
    return amount


def looks_like_pdf(fetch: FetchResult) -> bool:
    ct = (fetch.content_type or "").lower()
    return ("application/pdf" in ct) or fetch.url.lower().endswith(".pdf")


def extract_from_pdf(fetch: FetchResult) -> List[Dict[str, Any]]:
    date_patterns = [
        # As on November 30, 2025
        r"As\s+on\s+([A-Za-z]+ \d{1,2}, \d{4})",

        # As on 30 November 2025
        r"As\s+on\s+(\d{1,2} [A-Za-z]+ \d{4})",

        # As on 30.11.2025
        r"As\s+on\s+(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
    ]

    rows: List[Dict[str, Any]] = []
    with pdfplumber.open(io.BytesIO(fetch.body)) as pdf:
        for page in pdf.pages:
            ason_text = ""
            text = page.extract_text() or ""
            for pattern in date_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    ason_text = match.group(1)

            tables = page.extract_tables() or []
            if not tables:
                rows.extend(_extract_portfolio_rows_from_pdf_text(text, ason_text))
                continue
            for tbl in tables:
                if not tbl or len(tbl) < 2:
                    continue
                header = [str(x).strip() if x else "" for x in tbl[0]]
                
                # If headers have duplicates or empties, use col_0, col_1, col_2 instead
                if len(header) != len(set(h for h in header if h)) or any(not h for h in header):
                    header = [f"col_{i}" for i in range(len(header))]
                
                for r in tbl[1:]:
                    vals = [str(x).strip() if x else "" for x in r]
                    if not any(v.strip() for v in vals):
                        continue
                    row = {header[i] if i < len(header) else f"col_{i}": vals[i] for i in range(len(vals))}
                    row['ason'] = parse_date_any(ason_text)
                    rows.append(row)
    return rows


def _extract_portfolio_rows_from_pdf_text(text: str, ason_text: str) -> List[Dict[str, Any]]:
    """
    Fallback parser for PDF disclosures where tables are rendered as plain text lines
    (e.g., FinAGG). Detects lines that start with "Portfolio" and captures amount/FLDG.
    """
    if not text:
        return []

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
def extract_from_html_tables(fetch: FetchResult) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(fetch.body, "html.parser")
    tables = soup.find_all("table")
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
    if scrape_ts is None:
        scrape_ts = dt.datetime.utcnow()

    text = _clean_html_to_text(html)
    
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
        except:
            pass  # Fall through to CRED-style parsing

    """
    This works for cred. Can include more such cases on need basis with conditions
    """
    rows = parse_cred_style_dlg_plain_text(text)

    return rows


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
    as_on_txt = None
    if isinstance(as_on_cfg, dict):
        as_on_txt = as_on_cfg.get("constant")

    return [{
        "LSP Name": lsp_name,
        "Lender": None,
        "Portfolio": f"Grand Total ({portfolio_count} portfolios)",
        "Amount": amount,
        "AsOnTimestamp": parse_date_any(as_on_txt),
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
    
    # Parse constant date if provided
    as_on_date = None
    if isinstance(as_on_config, dict) and "constant" in as_on_config:
        try:
            as_on_date = dateparser.parse(as_on_config["constant"])
        except:
            pass
    
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
    scrape_ts = dt.datetime.utcnow()

    # Normalize newlines and spaces
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
    deduped = []
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

    return deduped


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
    for k in keys:
        if k in rr and rr[k] is not None and str(rr[k]).strip():
            return str(rr[k]).strip()
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
    m = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    try:
        return m.group(group).strip()
    except Exception:
        return None


# noinspection PyArgumentList
def page_level_values(fetch: FetchResult, rules: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    page_rules = rules.get("page_level") or {}

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
        v = extract_by_regex(body_text, as_on_regex, group=grp)
        if v:
            out["as_on"] = v

    return out


def normalize_rows(
        raw_rows: List[Dict[str, Any]],
        fetch: FetchResult,
        lsp_name: str,
        scrape_ts: dt.datetime,
        rules_json: Optional[str]
) -> Tuple[List[Dict[str, Any]], bool]:
    rules = load_rules(rules_json)
    field_map = rules.get("field_map") or {}
    page_vals = page_level_values(fetch, rules)

    defaults = {
        "lender": ["Lender", "Lending Partner", "Partner", "NBFC", "Bank"],
        "portfolio": ["Portfolio", "DLG set", "Cohort", "Set", "Portfolio Name"],
        "amount": ["Amount", "Outstanding AUM", "AUM", "Outstanding", "DLG Amount", "Outstanding AUM (₹ crores)",
                   "Outstanding AUM (INR crore)"],
        "as_on": ["As on", "As-on", "AsOn", "As on date", "Date", "AsOnTimestamp"],
    }

    def get_field(raw_row: Dict[str, Any], fname: str) -> Optional[str]:
        spec = field_map.get(fname)
        
        # Handle simple string mapping like "portfolio": "Portfolio"
        if isinstance(spec, str):
            return pick_by_keys(raw_row, [spec])
        
        # Handle dict-based spec
        if not isinstance(spec, dict):
            spec = {}
            
        if "constant" in spec and spec["constant"] is not None:
            return str(spec["constant"]).strip()
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
    for rr in raw_rows:
        # Check if row is already normalized (has capital-case keys from plain_text parsers)
        # Plain text parsers like extract_from_regex_patterns and parse_cred_style_dlg_plain_text
        # return pre-normalized rows with keys: LSP Name, Lender, Portfolio, Amount, AsOnTimestamp, ScrapeTimestamp
        force_include = False
        if "Amount" in rr and "Portfolio" in rr:
            # Row is already normalized, use directly
            lender_clean = rr.get("Lender")
            portfolio_clean = rr.get("Portfolio")
            normalized_amount = rr.get("Amount")
            ason = rr.get("AsOnTimestamp")
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
                if portfolio_str and portfolio_str != "None":
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

    for r in final_data:
        if r["Portfolio"] is None or r["Amount"] is None or r["AsOnTimestamp"] is None:
            partial = True

    return final_data, partial


def is_header_row(row: Dict[str, Any]) -> bool:
    """
    Detect if a row is a header row based on common patterns.
    Returns True if the row appears to be a header.
    """
    portfolio = row.get("Portfolio")
    lender = row.get("Lender")
    amount = row.get("Amount")
    
    if not portfolio:
        return False
    
    portfolio_lower = str(portfolio).lower().strip()
    
    # Exact match header keywords (must be exact match, not just contain)
    exact_header_keywords = [
        "portfolio", "lender", "amount", "outstanding", "aum", "dlg",
        "name", "partner", "regulated entity", "business segment",
        "cohort", "set", "total no", "s.no", "s no", "serial", "sr", 
        "particulars", "portfolio name", "lender name"
    ]
    
    # Check if portfolio field is exactly a header keyword
    if portfolio_lower in exact_header_keywords:
        return True
    
    # Check if lender field is also exactly a header keyword
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
            
            # If current amount equals sum of others (within small tolerance for floating point)
            if abs(current_amount - other_sum) < 0.01:
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