import re
import io
import json
import datetime as dt
from bs4 import BeautifulSoup
from dateutil import parser as dateparser
from typing import Any, Dict, List, Optional, Tuple
from models import FetchResult
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
            for tbl in tables:
                if not tbl or len(tbl) < 2:
                    continue
                header = [str(x).strip() if x else "" for x in tbl[0]]
                for r in tbl[1:]:
                    vals = [str(x).strip() if x else "" for x in r]
                    if not any(v.strip() for v in vals):
                        continue
                    row = {header[i] if i < len(header) else f"col_{i}": vals[i] for i in range(len(vals))}
                    row['ason'] = parse_date_any(ason_text)
                    rows.append(row)
    return rows


# noinspection PyArgumentList
def extract_from_html_tables(fetch: FetchResult) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(fetch.body, "html.parser")
    tables = soup.find_all("table")
    rows: List[Dict[str, Any]] = []
    for t in tables:
        trs = t.find_all("tr")
        if len(trs) < 2:
            continue
        headers = [c.get_text(separator=" ", strip=True) for c in trs[0].find_all(["th", "td"])]
        if not any(headers):
            continue
        for tr in trs[1:]:
            cells = tr.find_all(["td", "th"])
            vals = [c.get_text(separator=" ", strip=True) for c in cells]
            if not any(v.strip() for v in vals):
                continue
            rows.append({headers[i] if i < len(headers) else f"col_{i}": vals[i] for i in range(len(vals))})
    return rows


def extract_dlg_from_plain_text(
        html: bytes,
        lsp_name: str,
        scrape_ts: Optional[dt.datetime] = None
) -> List[Dict[str, Any]]:
    """
    Extract DLG disclosures from a page where data is in plain text (not HTML tables).

    Output schema:
      LSP Name, Lender, Portfolio, Amount, AsOnTimestamp, ScrapeTimestamp
    """
    if scrape_ts is None:
        scrape_ts = dt.datetime.utcnow()

    text = _clean_html_to_text(html)

    """
    This works for cred. Can include more such cases on need basis with conditions
    """
    rows = parse_cred_style_dlg_plain_text(text)

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


def load_rules(rules_json: Optional[str]) -> Dict[str, Any]:
    if not rules_json:
        return {}
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
        spec = field_map.get(fname) or {}
        if "constant" in spec and spec["constant"] is not None:
            return str(spec["constant"]).strip()
        keys = spec.get("keys") or defaults[fname]
        val = pick_by_keys(raw_row, keys)
        if val and spec.get("regex"):
            grp = int(spec.get("group", 1))
            val2 = extract_by_regex(val, spec["regex"], group=grp)
            return val2 if val2 else val
        return val

    out_rows: List[Dict[str, Any]] = []
    for rr in raw_rows:
        lender_txt = get_field(rr, "lender") or page_vals.get("lender")
        portfolio_txt = get_field(rr, "portfolio") or page_vals.get("portfolio")
        amount_txt = get_field(rr, "amount") or page_vals.get("amount")
        ason_txt = get_field(rr, "as_on") or page_vals.get("as_on")

        # if not parse_amount_any(amount_txt):
        #     continue

        row = {
            "LSP Name": lsp_name,
            "Lender": str(lender_txt).strip() if lender_txt and str(lender_txt).strip() else None,
            "Portfolio": str(portfolio_txt).strip() if portfolio_txt and str(portfolio_txt).strip() else None,
            "Amount": parse_amount_any(amount_txt),
            "AsOnTimestamp": parse_date_any(ason_txt),
            "ScrapeTimestamp": scrape_ts,
        }

        if row["Lender"] is None and row["Portfolio"] is None and row["Amount"] is None and row[
            "AsOnTimestamp"] is None:
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

    for r in final_data:
        if r["Portfolio"] is None or r["Amount"] is None or r["AsOnTimestamp"] is None:
            partial = True

    return final_data, partial


def merge_partial_rows(rows: List[dict[str, Any]]) -> List[dict[str, Any]]:
    return rows
