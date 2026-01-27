import datetime as dt
from http import HTTPStatus
from flask import request, jsonify, Blueprint
from typing import List, Optional, Tuple, Dict, Any
from utils.logger_config import logger_method

from General.Service.DlgCrawlerService import DlgCrawlerService
from General.Service.LspMasterService import LSPMasterService

"""User-facing entry point that wires inputs to the crawler manager."""
crawler_bp = Blueprint('crawler_bp', __name__)

logger = logger_method(__name__)
crawler_service = DlgCrawlerService()
lsp_service = LSPMasterService()


@crawler_bp.post("/api/scrape")
def handle_trigger_scrape():
    """Handle manual scrape trigger request."""
    lsp_id = request.args.get("lsp_id", default=0, type=int)

    try:
        count = run_scrape(lsp_id=lsp_id)
        if count > 0:
            return jsonify({"status": HTTPStatus.OK, "message": f"Scrape completed", "data": lsp_id}), HTTPStatus.OK
        else:
            return jsonify({"status": HTTPStatus.NOT_FOUND, "message": f"Scrape Not Done"}), HTTPStatus.NOT_FOUND
    except Exception as exc:
        logger.error(f"Error triggering scrape: {str(exc)}", exc_info=True)
        return jsonify(
            {"status": HTTPStatus.INTERNAL_SERVER_ERROR,
             "message": f'Error Scrapping {lsp_id}'}), HTTPStatus.INTERNAL_SERVER_ERROR


def run_scrape(lsp_id: Optional[int] = 0) -> int:
    sources = lsp_service.load_active(lsp_id)
    if sources:
        crawler_service.run_scrape_sources(sources)
        return len(sources)
    else:
        logger.critical('No LSP Found')
        return 0
