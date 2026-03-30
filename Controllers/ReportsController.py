from http import HTTPStatus
from utils.logger_config import logger_method
from utils.jwt_utils import token_required
from flask import request, jsonify, Blueprint
import pandas as pd
from datetime import datetime, timedelta

from Service.ReportsService import ReportsService

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from utils.rate_limiter import limiter

"""Controller for Reports API operations."""

reports_bp = Blueprint('reports_bp', __name__)

logger = logger_method(__name__)


@reports_bp.post("/api/reports/summarize_lsp")
@token_required
@limiter.limit("10 per minute")
def summarize_lsp():
    """Handle LSP summarization request.
    
    Expected JSON payload:
    {
        "start_date": "2024-01-01",  # or datetime
        "end_date": "2024-12-31"     # or datetime
    }
    """
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"

    payload = request.get_json(silent=True)

    try:
        start_date = None
        end_date = None
        if payload:
            start_date = payload.get('start_date')
            end_date = payload.get('end_date')

        # Set defaults if not provided: 15th of last month to 15th of this month
        today = datetime.now()
        if not start_date:
            # 15th of last month
            start_date = (today.replace(day=1) - timedelta(days=1)).replace(day=15)
            logger.info(f"{user_info} Using default start_date: {start_date.date()}")
        
        if not end_date:
            # 15th of this month
            end_date = today.replace(day=15)
            logger.info(f"{user_info} Using default end_date: {end_date.date()}")

        # Normalize dates using pandas (dayfirst=True for DD/MM/YYYY or DD-MM-YYYY format)
        try:
            start_dt = pd.to_datetime(start_date, dayfirst=True)
            end_dt = pd.to_datetime(end_date, dayfirst=True) + pd.Timedelta(days=1)
        except Exception as e:
            logger.warning(f"{user_info} Invalid date format: {e}")
            return jsonify(
                {"status": HTTPStatus.BAD_REQUEST, 
                 "message": f'Invalid date format: {str(e)}',
                 "user_info": user_info}), HTTPStatus.BAD_REQUEST

        logger.info(f"{user_info} Starting LSP summarization from {start_dt} to {end_dt}")
        reports_service = ReportsService(user_claims)
        upserted = reports_service.run_lsp_summarize(start_dt, end_dt)

        logger.info(f"{user_info} LSP summarization completed: {upserted} rows upserted")
        return jsonify({
            "status": HTTPStatus.OK,
            "message": "LSP summarization completed successfully",
            "user_info": user_info,
            "data": {
                "upserted": upserted,
                "start_date": str(start_dt.date()),
                "end_date": str(end_dt.date())
            }
        }), HTTPStatus.OK

    except Exception as exc:
        logger.critical(f"{user_info} Error during LSP summarization: {str(exc)}", exc_info=True)
        return jsonify(
            {"status": HTTPStatus.INTERNAL_SERVER_ERROR,
             "message": f"Error during LSP summarization: {str(exc)}",
             "user_info": user_info}), HTTPStatus.INTERNAL_SERVER_ERROR
