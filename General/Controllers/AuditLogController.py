import datetime as dt
from http import HTTPStatus
from DatabaseOperation.DatabaseModels.orm_models import AuditAction
from utils.logger_config import logger_method
from flask import request, jsonify, Blueprint

from General.Service.AuditLogService import AuditLogService

auditlog_bp = Blueprint('auditlog_bp', __name__)

logger = logger_method(__name__)
audit_service = AuditLogService()


@auditlog_bp.get("/api/auditlog")
def handle_list_audit_log():
    """Handle audit log list request."""
    try:
        page = request.args.get('page', default=1, type=int)
        page_size = request.args.get('page_size', default=10, type=int)
        lsp_id = request.args.get('lsp_id', default=0, type=int)
        action_str = request.args.get("action", default="", type=str)
        start = request.args.get("start", default=(dt.datetime.now() - dt.timedelta(30)).strftime('%d-%m-%Y'),
                                 type=str)
        end = request.args.get("end", default=dt.datetime.now().strftime('%d-%m-%Y'),
                               type=str)
        action = getattr(AuditAction, action_str.upper(), None)
        if not action:
            action_str = None
        start_date = dt.datetime.strptime(start, '%d-%m-%Y')
        end_date = dt.datetime.strptime(end, '%d-%m-%Y')
    except Exception as ex:
        message = f'exception while extracting arguments {str(ex)}'
        logger.exception(message)
        return jsonify(
            {"status": HTTPStatus.BAD_REQUEST, "message": message}), HTTPStatus.BAD_REQUEST
    try:
        results, rows = audit_service.list_audit_logs(start_date=start_date, end_date=end_date, lsp_id=lsp_id,
                                                      action_str=action, page=page, page_size=page_size)
        if rows > 0:
            return jsonify({"status": HTTPStatus.OK, "message": "Audit Logs Fetched", "data": results,
                            "count": rows}), HTTPStatus.OK
        else:
            logger.info(f"No Audit logs found for the given filters")
            return jsonify(
                {"status": HTTPStatus.NOT_FOUND,
                 "message": 'No Audit logs found for the given filters'}), HTTPStatus.NOT_FOUND
    except Exception as exc:
        logger.critical(f"Exception Listing Audit Logs: {str(exc)}", exc_info=True)
        return jsonify(
            {"status": HTTPStatus.INTERNAL_SERVER_ERROR, "message": str(exc)}), HTTPStatus.INTERNAL_SERVER_ERROR

# For Testing never called via API. called internally
# @auditlog_bp.post("/api/auditlog")
# def handle_add_audit_log():
#     """Handle audit log list request."""
#     try:
#         payload = request.get_json(silent=True)
#         if not payload:
#             return jsonify(
#                 {"status": HTTPStatus.BAD_REQUEST, "message": 'No Data found'}), HTTPStatus.BAD_REQUEST
#
#         audit_log = AuditLog(**payload)
#     except Exception as ex:
#         message = f'exception while extracting arguments {str(ex)}'
#         logger.exception(message)
#         return jsonify(
#             {"status": HTTPStatus.BAD_REQUEST, "message": message}), HTTPStatus.BAD_REQUEST
#     try:
#         success = audit_service.record(
#             audit_service.build(audit_log.lsp_id, audit_log.action_taken, audit_log.auto_manual, audit_log.user_id,
#                                 audit_log.payload))
#         if success:
#             return jsonify({"status": HTTPStatus.OK, "message": "Audit Logs Added"}), HTTPStatus.OK
#         else:
#             logger.info(f"Audit Log Add Failed")
#             return jsonify(
#                 {"status": HTTPStatus.NOT_FOUND, "message": 'No Audit logs found for the given filters'}), HTTPStatus.NOT_FOUND
#     except Exception as exc:
#         logger.critical(f"Exception Listing Audit Logs: {str(exc)}", exc_info=True)
#         return jsonify(
#             {"status": HTTPStatus.INTERNAL_SERVER_ERROR, "message": str(exc)}), HTTPStatus.INTERNAL_SERVER_ERROR
