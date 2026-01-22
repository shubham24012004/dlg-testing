from flask import Request

import datetime as dt
import json
from typing import List, Optional, Tuple, Dict, Any
from utils.logger_config import logger_method
from DatabaseOperation.DatabaseModels.orm_models import AuditAction, LspMaster
from General.Service.AuditLogService import AuditLogService
from General.Service.DlgCrawlerService import DlgCrawlerService
from General.Service.LspMasterService import LSPMasterService


class DlgCrawlerController:
    """User-facing entry point that wires inputs to the crawler manager."""

    def __init__(self):
        self.logger = logger_method(__name__)
        self.crawler_service = DlgCrawlerService()
        self.lsp_service = LSPMasterService()
        self.auditlog_service = AuditLogService()

    def handle_trigger_scrape(self, request: Request, crawler_controller) -> Tuple[Dict[str, Any], int]:
        """Handle manual scrape trigger request."""
        payload = request.get_json(silent=True) or {}
        limit = payload.get("limit")
        lsp_id = payload.get("lsp_id")

        try:
            self.run_scrape(limit=limit, lsp_id=lsp_id)
            return {"status": "ok", "limit": limit, "lsp_id": lsp_id}, 200
        except Exception as exc:
            self.logger.error("Error triggering scrape: %s", str(exc), exc_info=True)
            return {"status": "error", "message": str(exc)}, 500

    def run_scrape(self, limit: Optional[int] = None, lsp_id: Optional[str] = None) -> None:
        sources = self.lsp_service.load_active()
        if lsp_id:
            sources = [s for s in sources if (s.lsp_id and str(s.lsp_id) == str(lsp_id)) or (
                s.id == int(lsp_id) if str(lsp_id).isdigit() else False)]
        self.run_scrape_sources(sources, limit)

    def run_scrape_sources(self, sources: List[LspMaster], limit: Optional[int] = None) -> None:
        if limit:
            sources = sources[:limit]

        for source in sources:
            scrape_started_at = dt.datetime.utcnow()
            try:
                status, *_rest, normalized_rows = self.crawler_service.scrape_one(source)
                self.crawler_service.persist_rows(status, normalized_rows, source, scrape_started_at)
                self.auditlog_service.audit_manager.record(
                    self.auditlog_service.audit_manager.build(
                        lsp_id=(source.lsp_id or source.lsp_name),
                        action_taken=AuditAction.CRAWL,
                        auto_manual="auto",
                        user_id="system",
                        payload=json.dumps({"status": status, "details": None, "ts": scrape_started_at.isoformat()}),
                    )
                )
                print(f"[OK] {source.lsp_name} -> {status}")
            except Exception as exc:  # pragma: no cover - operational safety
                self.crawler_service.persist_error(source, scrape_started_at)
                self.auditlog_service.audit_manager.record(
                    self.auditlog_service.audit_manager.build(
                        lsp_id=(source.lsp_id or source.lsp_name),
                        action_taken=AuditAction.CRAWL,
                        auto_manual="auto",
                        user_id="system",
                        payload=json.dumps(
                            {"status": "Error", "details": str(exc)[:200], "ts": scrape_started_at.isoformat()}),
                    )
                )
                print(f"[ERR] {source.lsp_name} -> Error ({str(exc)[:120]})")


__all__ = ["DlgCrawlerController"]
