from __future__ import annotations

import datetime as dt
import json
from typing import List, Optional

from DatabaseOperation.SQLAlchemy.DatabaseModels import AuditAction, LspMaster
from General.Managers.DlgCrawlerManager import DlgCrawlerManager


class DlgCrawlerController:
    """User-facing entry point that wires inputs to the crawler manager."""

    def __init__(self, manager: Optional[DlgCrawlerManager] = None) -> None:
        self.manager = manager or DlgCrawlerManager()

    def run_scrape(self, limit: Optional[int] = None, lsp_id: Optional[str] = None) -> None:
        sources = self.manager.lsp_manager.load_active()
        if lsp_id:
            sources = [s for s in sources if (s.lsp_id and str(s.lsp_id) == str(lsp_id)) or (s.id == int(lsp_id) if str(lsp_id).isdigit() else False)]
        self.run_scrape_sources(sources, limit)

    def run_scrape_sources(self, sources: List[LspMaster], limit: Optional[int] = None) -> None:
        if limit:
            sources = sources[:limit]

        for source in sources:
            scrape_started_at = dt.datetime.utcnow()
            try:
                status, *_rest, normalized_rows = self.manager.scrape_one(source)
                self.manager.persist_rows(status, normalized_rows, source, scrape_started_at)
                self.manager.audit_manager.record(
                    self.manager.audit_manager.build(
                        lsp_id=(source.lsp_id or source.lsp_name),
                        action_taken=AuditAction.CRAWL,
                        auto_manual="auto",
                        user_id="system",
                        payload=json.dumps({"status": status, "details": None, "ts": scrape_started_at.isoformat()}),
                    )
                )
                print(f"[OK] {source.lsp_name} -> {status}")
            except Exception as exc:  # pragma: no cover - operational safety
                self.manager.persist_error(source, scrape_started_at)
                self.manager.audit_manager.record(
                    self.manager.audit_manager.build(
                        lsp_id=(source.lsp_id or source.lsp_name),
                        action_taken=AuditAction.CRAWL,
                        auto_manual="auto",
                        user_id="system",
                        payload=json.dumps({"status": "Error", "details": str(exc)[:200], "ts": scrape_started_at.isoformat()}),
                    )
                )
                print(f"[ERR] {source.lsp_name} -> Error ({str(exc)[:120]})")
