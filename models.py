from dataclasses import dataclass
from typing import Optional


# -----------------------------
# TYPES
# -----------------------------

@dataclass
class SourceRow:
    lsp_name: str
    disclosure_url: str
    is_active: bool
    fetch_hint: str  # auto|requests|playwright
    parse_hint: str  # auto|html_table|pdf_table
    rules_json: Optional[str]


@dataclass
class FetchResult:
    url: str
    status_code: int
    content_type: str
    body: bytes
    fetch_mode_used: str  # requests|playwright
