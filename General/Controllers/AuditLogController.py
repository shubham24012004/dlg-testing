import datetime as dt
from http import HTTPStatus
from DatabaseOperation.DatabaseModels.master_models import AuditAction
from utils.logger_config import logger_method
from utils.jwt_utils import token_required
from flask import request, jsonify, Blueprint

from General.Service.AuditLogService import AuditLogService

auditlog_bp = Blueprint('auditlog_bp', __name__)

logger = logger_method(__name__)


@auditlog_bp.get("/api/auditlog")
@token_required
def handle_list_audit_log():
    """Handle audit log list request."""
    # Access user details from JWT token
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"
    
    try:
        page = request.args.get('page', default=1, type=int)
        page_size = request.args.get('page_size', default=10, type=int)
        lsp_id = request.args.get('lsp_id', default=0, type=int)
        action_str = request.args.get("action", default="", type=str)
        start = request.args.get("start", default=(dt.datetime.now() - dt.timedelta(30)).strftime('%d-%m-%Y'),
                                 type=str)
        end = request.args.get("end", default=(dt.datetime.now() + dt.timedelta(1)).strftime('%d-%m-%Y'),
                               type=str)
        action = getattr(AuditAction, action_str.upper(), None)
        if not action:
            action_str = None
        start_date = dt.datetime.strptime(start, '%d-%m-%Y')
        end_date = dt.datetime.strptime(end, '%d-%m-%Y')
    except Exception as ex:
        message = f'exception while extracting arguments {str(ex)}'
        logger.exception(f"{user_info} {message}")
        return jsonify(
            {"status": HTTPStatus.BAD_REQUEST, "message": message, "user_info": user_info}), HTTPStatus.BAD_REQUEST
    try:
        audit_service = AuditLogService(user_claims)
        results, rows = audit_service.list_audit_logs(start_date=start_date, end_date=end_date, lsp_id=lsp_id,
                                                      action_str=action, page=page, page_size=page_size)
        if rows > 0:
            logger.info(f"{user_info} Audit Logs Fetched successfully - Count: {rows}")
            return jsonify({"status": HTTPStatus.OK, "message": "Audit Logs Fetched", "user_info": user_info, "data": results,
                            "count": rows}), HTTPStatus.OK
        else:
            logger.info(f"{user_info} No Audit logs found for the given filters")
            return jsonify(
                {"status": HTTPStatus.NOT_FOUND,
                 "message": "No Audit logs found for the given filters", "user_info": user_info}), HTTPStatus.NOT_FOUND
    except Exception as exc:
        logger.critical(f"{user_info} Exception Listing Audit Logs: {str(exc)}", exc_info=True)
        return jsonify(
            {"status": HTTPStatus.INTERNAL_SERVER_ERROR, "message": f"Exception: {str(exc)}", "user_info": user_info}), HTTPStatus.INTERNAL_SERVER_ERROR
