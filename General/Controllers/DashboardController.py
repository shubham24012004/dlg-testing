from http import HTTPStatus
from utils.logger_config import logger_method
from utils.jwt_utils import token_required
from flask import request, jsonify, Blueprint
import pandas as pd
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from General.Service.ReportsService import ReportsService

"""Controller for Reports API operations."""

dashboard_bp = Blueprint('dashboard_bp', __name__)

logger = logger_method(__name__)


@dashboard_bp.get("/api/dashboard/lsp_summary")
@token_required
def lsp_summary():
    """Get lsp_summary Table data."""

    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"

    try:
        logger.info(f"{user_info} Getting LSP summaries for Dashboard")
        reports_service = ReportsService(user_claims)
        result, count = reports_service.get_summaries()

        logger.info(f"{user_info} Get LSP summaries completed: {count} rows returned")
        return jsonify({
            "status": HTTPStatus.OK,
            "message": "LSP summarization completed successfully",
            "user_info": user_info,
            "data": {"result": result, "count": count}
        }), HTTPStatus.OK

    except Exception as exc:
        logger.critical(f"{user_info} Error during Get LSP summaries: {str(exc)}", exc_info=True)
        return jsonify(
            {"status": HTTPStatus.INTERNAL_SERVER_ERROR,
             "message": f"Error during LSP summarization: {str(exc)}",
             "user_info": user_info}), HTTPStatus.INTERNAL_SERVER_ERROR
