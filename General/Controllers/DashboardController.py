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
        result, count = reports_service.get_latest_summary()

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


@dashboard_bp.get("/api/dashboard/all_lsp_all_summary")
@token_required
def all_lsp_all_summary():
    """Get lsp_summary Table data."""

    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"

    try:
        start_year = datetime.now().year - 1
        end_year = datetime.now().year
        start_month = 1
        end_month = 12
        lsp_id = None
        payload = request.get_json(silent=True)


        if payload:
            start_year = payload.get('start_year')
            end_year = payload.get('end_year')
            start_month = payload.get('start_month')
            end_month = payload.get('end_month')
            lsp_id = payload.get('lsp_id')

        logger.info(f"{user_info} Getting All LSP summaries for Dashboard")
        reports_service = ReportsService(user_claims)
        result, count = reports_service.get_all_summaries(start_year=start_year, end_year=end_year,
                                                          start_month=start_month, end_month=end_month, lsp_id=lsp_id)

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
    if lsp_id is None:
        return jsonify(
            {"status": HTTPStatus.BAD_REQUEST,
             "message": "lsp_id query parameter is required",
             "user_info": user_info
             }), HTTPStatus.BAD_REQUEST

    try:
        logger.info(f"{user_info} Getting LSP raw data for LSP ID: {lsp_id} for Dashboard")
        reports_service = ReportsService(user_claims)
        result, count = reports_service.get_raw_data(lsp_id)

        logger.info(f"{user_info} Get LSP raw data completed: {count} rows returned for LSP ID: {lsp_id}")
        return jsonify({
            "status": HTTPStatus.OK,
            "message": "LSP raw data retrieval completed successfully",
            "user_info": user_info,
            "data": {"result": result, "count": count}
        }), HTTPStatus.OK

    except Exception as exc:
        logger.critical(f"{user_info} Error during Get LSP raw data for LSP ID: {lsp_id}: {str(exc)}", exc_info=True)
        return jsonify(
            {"status": HTTPStatus.INTERNAL_SERVER_ERROR,
             "message": f"Error during LSP raw data retrieval for LSP ID: {lsp_id}: {str(exc)}",
             "user_info": user_info}), HTTPStatus.INTERNAL_SERVER_ERROR
