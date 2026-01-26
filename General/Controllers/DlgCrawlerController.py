from flask import Request

from typing import List, Optional, Tuple, Dict, Any
from utils.logger_config import logger_method


from General.Service.DlgCrawlerService import DlgCrawlerService



class DlgCrawlerController:
    """User-facing entry point that wires inputs to the crawler manager."""

    def __init__(self):
        self.logger = logger_method(__name__)
        self.crawler_service = DlgCrawlerService()


    def handle_trigger_scrape(self, request: Request, crawler_controller) -> Tuple[Dict[str, Any], int]:
        """Handle manual scrape trigger request."""
        payload = request.get_json(silent=True) or {}
        lsp_id = payload.get("lsp_id")

        try:
            self.run_scrape(lsp_id=lsp_id)
            return {"status": "ok", "lsp_id": lsp_id}, 200
        except Exception as exc:
            self.logger.error("Error triggering scrape: {0}", str(exc), exc_info=True)
            return {"status": "error", "message": str(exc)}, 500

    def run_scrape(self, lsp_id: Optional[int] = None) -> None:
        sources = self.lsp_service.load_active(lsp_id)
        if sources:
            self.crawler_service.run_scrape_sources(sources)
        else:
            self.logger.critical('No LSP Found')




__all__ = ["DlgCrawlerController"]
