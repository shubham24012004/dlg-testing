"""SQLAlchemy-style data models for the DLG analysis domain.

These dataclasses keep the project structure aligned with the CloudM-style
"DatabaseOperation" package so that managers/controllers can depend on a single
set of types regardless of the persistence layer (CSV today, real DB tomorrow).
"""
from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class AuditAction(Enum):
    """Enum for audit log actions, loaded from environment variables."""

    INSERT_LSP = os.getenv("AUDIT_ACTION_INSERT_LSP", "INSERT_LSP")
    UPDATE_LSP = os.getenv("AUDIT_ACTION_UPDATE_LSP", "UPDATE_LSP")
    DELETE_LSP = os.getenv("AUDIT_ACTION_DELETE_LSP", "DELETE_LSP")
    URL_FINDER = os.getenv("AUDIT_ACTION_URL_FINDER", "URL_FINDER")
    CRAWL = os.getenv("AUDIT_ACTION_CRAWL", "CRAWL")


@dataclass(slots=True)
class LspMaster:
    """Represents one row from the ``lsp_master`` table/CSV.

    `rules_json` is stored in the DB as JSON/text but represented in-memory
    as an already-parsed mapping (dict) when available.
    """
    lsp_name: str
    disclosure_url: str
    is_active: bool
    fetch_hint: str
    parse_hint: str
    rules_json: Optional[Dict[str, Any]] = None
    lsp_id: Optional[str] = None
    home_url: Optional[str] = None
    id: Optional[int] = None


# Backwards-compatibility alias used by legacy modules that still reference
# ``SourceRow``.  This keeps the refactor incremental.
SourceRow = LspMaster


@dataclass(slots=True)
class DlgCrawlerConfig:
    """High-level knobs that control how a disclosure is fetched/parsed.

    `rules_json` is represented in-memory as a mapping (dict) when available.
    """

    fetch_hint: str = "auto"
    parse_hint: str = "auto"
    pre_click_js: Optional[str] = None
    rules_json: Optional[Dict[str, Any]] = None


@dataclass(slots=True)
class DlgRaw:
    """One normalized disclosure row stored in ``dlg_raw``."""

    lsp_name: str
    lender: Optional[str]
    portfolio: Optional[str]
    amount: Optional[float]
    as_on_timestamp: Optional[dt.datetime]
    scrape_timestamp: Optional[dt.datetime]
    complete: str
    lsp_id: Optional[str] = None


@dataclass(slots=True)
class AuditLog:
    """Minimal structure for writing audit events to ``audit_log``."""

    lsp_id: str
    action_taken: AuditAction
    auto_manual: str
    user_id: str
    payload: Optional[str]
    created_at: dt.datetime = field(default_factory=dt.datetime.utcnow)


@dataclass(slots=True)
class FetchResult:
    """Transport object used by fetchers/normalizers."""

    url: str
    status_code: int
    content_type: str
    body: bytes
    fetch_mode_used: str


def dlg_raw_from_dict(payload: Dict[str, Any], status: str) -> DlgRaw:
    """Helper to convert legacy dict rows into ``DlgRaw`` dataclasses."""

    return DlgRaw(
        lsp_name=payload.get("LSP Name"),
        lender=payload.get("Lender"),
        portfolio=payload.get("Portfolio"),
        amount=payload.get("Amount"),
        as_on_timestamp=payload.get("AsOnTimestamp"),
        scrape_timestamp=payload.get("ScrapeTimestamp"),
        complete=status,
    )
