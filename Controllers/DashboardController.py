from http import HTTPStatus
from utils.constants import AuditAction, CrawlStatus, LSPType
from utils.logger_config import logger_method
from utils.jwt_utils import token_required
from flask import request, jsonify, Blueprint
from datetime import datetime

from Service.ReportsService import ReportsService

"""Controller for Reports API operations."""

dashboard_bp = Blueprint('dashboard_bp', __name__)

logger = logger_method(__name__)


@dashboard_bp.get("/api/dashboard/all_lsp_latest_summary")
@token_required
def all_lsp_latest_summary():
    """Get lsp_summary Table data."""

    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"

    try:
        logger.info(f"{user_info} Getting LSP summaries for Dashboard")
        reports_service = ReportsService(user_claims)
        result, count, portfolio_count, amount, lenders_count = reports_service.get_latest_summary()

        logger.info(f"{user_info} Get LSP summaries completed: {count} rows returned")
        return jsonify({
            "status": HTTPStatus.OK,
            "message": "LSP summarization completed successfully",
            "user_info": user_info,
            "data": {"result": result, "count": count, "portfolio_count": portfolio_count, "amount": amount,
                     "lenders_count": lenders_count}
        }), HTTPStatus.OK

    except Exception as exc:
        logger.critical(f"{user_info} Error during Get LSP summaries: {str(exc)}", exc_info=True)
        return jsonify(
            {"status": HTTPStatus.INTERNAL_SERVER_ERROR,
             "message": f"Error during LSP summarization: {str(exc)}",
             "user_info": user_info}), HTTPStatus.INTERNAL_SERVER_ERROR


@dashboard_bp.post("/api/dashboard/all_lsp_all_summary")
@token_required
def all_lsp_all_summary():
    """Get lsp_summary Table data."""

    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"

    try:
        year = datetime.now().year
        lsp_id = None
        status = None
        payload = request.get_json(silent=True)

        if payload:
            year = payload.get('year', year)
            lsp_id = payload.get('lsp_id', lsp_id)
            status = payload.get('status', status)

        logger.info(f"{user_info} Getting All LSP summaries for Dashboard")
        reports_service = ReportsService(user_claims)
        result, count = reports_service.get_all_summaries(year=year, lsp_id=lsp_id, status=status)

        logger.info(f"{user_info} Get All LSP summaries completed: {count} rows returned")
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


@dashboard_bp.get("/api/dashboard/lsp_raw")
@token_required
def lsp_raw():
    """Get lsp_raw Table data for a specific LSP ID."""

    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"
    lsp_id = request.args.get('lsp_id', type=int)
    month = request.args.get('month', type=int)
    year = request.args.get('year', type=int)
    if lsp_id is None or month is None or year is None:
        return jsonify(
            {"status": HTTPStatus.BAD_REQUEST,
             "message": "lsp_id, month, and year query parameters are required",
             "user_info": user_info
             }), HTTPStatus.BAD_REQUEST

    try:
        logger.info(f"{user_info} Getting LSP raw data for LSP ID: {lsp_id} for Dashboard")
        reports_service = ReportsService(user_claims)
        result, count, portfolio_count, amount, lenders_count = reports_service.get_raw_data(lsp_id, month=month,
                                                                                             year=year)

        logger.info(f"{user_info} Get LSP raw data completed: {count} rows returned for LSP ID: {lsp_id}")
        return jsonify({
            "status": HTTPStatus.OK,
            "message": "LSP raw data retrieval completed successfully",
            "user_info": user_info,
            "data": {"result": result, "count": count, "portfolio_count": portfolio_count, "amount": amount,
                     "lenders_count": lenders_count}
        }), HTTPStatus.OK

    except Exception as exc:
        logger.critical(f"{user_info} Error during Get LSP raw data for LSP ID: {lsp_id}: {str(exc)}", exc_info=True)
        return jsonify(
            {"status": HTTPStatus.INTERNAL_SERVER_ERROR,
             "message": f"Error during LSP raw data retrieval for LSP ID: {lsp_id}: {str(exc)}",
             "user_info": user_info}), HTTPStatus.INTERNAL_SERVER_ERROR


@dashboard_bp.post("/api/dashboard/lsp_summary_graph")
@token_required
def get_summary_for_graph():
    """Get lsp_summary Table data for a specific LSP ID for graphing."""

    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"

    try:
        year = datetime.now().year
        lsp_id = None
        status = None
        payload = request.get_json(silent=True)

        if payload:
            year = payload.get('year', year)
            lsp_id = payload.get('lsp_id', lsp_id)
            status = payload.get('status', status)

        logger.info(f"{user_info} Getting LSP summary data for graphing for LSP ID: {lsp_id} for Dashboard")
        reports_service = ReportsService(user_claims)
        result, count = reports_service.get_summary_for_graph(lsp_id=lsp_id, status=status, year=year)

        logger.info(
            f"{user_info} Get LSP summary data for graphing completed: {count} rows returned for LSP ID: {lsp_id}")
        return jsonify({
            "status": HTTPStatus.OK,
            "message": "LSP summary data retrieval for graphing completed successfully",
            "user_info": user_info,
            "data": {"result": result, "count": count}
        }), HTTPStatus.OK

    except Exception as exc:
        logger.critical(f"{user_info} Error during Get LSP summary data for graphing for LSP ID: {lsp_id}: {str(exc)}",
                        exc_info=True)
        return jsonify(
            {"status": HTTPStatus.INTERNAL_SERVER_ERROR,
             "message": f"Error during LSP summary data retrieval for graphing for LSP ID: {lsp_id}: {str(exc)}",
             "user_info": user_info}), HTTPStatus.INTERNAL_SERVER_ERROR


@dashboard_bp.get("/api/dashboard/enums")
def get_enums():
    """Return all enum values for frontend use."""
    return jsonify({
        "lsp_types": [e.value for e in LSPType],
        "crawl_statuses": [e.value for e in CrawlStatus],
        "audit_actions": [e.value for e in AuditAction]
    }), HTTPStatus.OK
