import datetime as dt
from http import HTTPStatus
from flask import request, jsonify, Blueprint
from typing import List, Optional, Tuple, Dict, Any
from utils.logger_config import logger_method
from utils.jwt_utils import token_required

from General.Service.DlgCrawlerService import DlgCrawlerService
from General.Service.LspMasterService import LSPMasterService

"""User-facing entry point that wires inputs to the crawler manager."""
crawler_bp = Blueprint('crawler_bp', __name__)

logger = logger_method(__name__)
crawler_service = DlgCrawlerService()
lsp_service = LSPMasterService()


@crawler_bp.post("/api/scrape")
@token_required
def handle_trigger_scrape():
    """Handle manual scrape trigger request."""
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"
    lsp_id = request.args.get("lsp_id", default=0, type=int)

    try:
        count = run_scrape(lsp_id=lsp_id, user_claims=user_claims)
        if count > 0:
            logger.info(f"{user_info} Scrape completed for LSP ID: {lsp_id}")
            return jsonify({"status": HTTPStatus.OK, "message": "Scrape completed", "user_info": user_info, "data": lsp_id}), HTTPStatus.OK
        else:
            logger.warning(f"{user_info} Scrape not done for LSP ID: {lsp_id}")
            return jsonify({"status": HTTPStatus.NOT_FOUND, "message": "Scrape Not Done", "user_info": user_info}), HTTPStatus.NOT_FOUND
    except Exception as exc:
        logger.error(f"{user_info} Error triggering scrape: {str(exc)}", exc_info=True)
        return jsonify(
            {"status": HTTPStatus.INTERNAL_SERVER_ERROR,
             "message": f'Error Scrapping {lsp_id}', "user_info": user_info}), HTTPStatus.INTERNAL_SERVER_ERROR


def run_scrape(lsp_id: Optional[int] = 0, user_claims: Optional[Dict[str, Any]] = None) -> int:
    sources = lsp_service.load_active(lsp_id)
    if sources:
        crawler_service.run_scrape_sources(sources, user_claims=user_claims)
        return len(sources)
    else:
        logger.critical('No LSP Found')
        return 0
