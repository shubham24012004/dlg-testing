from http import HTTPStatus
from utils.logger_config import logger_method
from utils.jwt_utils import token_required
from flask import request, jsonify, Blueprint

from Service.LspMasterService import LSPMasterService
from DatabaseOperation.DatabaseModels.master_models import LspMasterIp, LspMaster

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from utils.rate_limiter import limiter

"""Controller for API operations with business logic."""

lsp_master_bp = Blueprint('lsp_master_bp', __name__)

logger = logger_method(__name__)



@lsp_master_bp.get("/api/lsp_master")
@token_required
@limiter.limit("10 per minute")
def handle_list_lsp_master():
    """Handle LSP master list request."""
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"
    try:
        active = request.args.get('active', default="True", type=str)
        active_flag = True
        if active.lower() == "false":
            active_flag = False

        page = request.args.get('page', default=1, type=int)
        per_page = request.args.get('per_page', default=10, type=int)
        lsp_id = request.args.get('lsp_id', default=0, type=int)
        lsp_name = request.args.get('lsp_name', default="", type=str)
        lsp_type = request.args.get('lsp_type', default="", type=str).strip()

        lsp_service = LSPMasterService(user_claims)
        results, total_count, rows = lsp_service.list_lsp_master(active_only=active_flag,
                                                                 page=page,
                                                                 per_page=per_page,
                                                                 lsp_id=lsp_id,
                                                                 lsp_name=lsp_name,
                                                                 lsp_type=lsp_type)
        logger.info(f"{user_info} Fetched LSP Master records: {rows}")
        if rows > 0:
            return jsonify({"status": HTTPStatus.OK, "message": "LSP fetched successfully", "user_info": user_info,
                            "data": results,
                            "count": total_count}), HTTPStatus.OK
        else:
            logger.info(f"{user_info} LSP Master record not found")
            return jsonify(
                {"status": HTTPStatus.NOT_FOUND, "message": 'LSP Not Found',
                 "user_info": user_info}), HTTPStatus.NOT_FOUND
    except Exception as exc:
        logger.critical(f"{user_info} Error listing LSP Master records: {str(exc)}", exc_info=True)
        return jsonify(
            {"status": HTTPStatus.INTERNAL_SERVER_ERROR, "message": str(exc),
             "user_info": user_info}), HTTPStatus.INTERNAL_SERVER_ERROR


@lsp_master_bp.post("/api/dlg_url")
@token_required
@limiter.limit("10 per minute")
def get_dlg_url():
    """Handle LSP master list request."""
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"
    try:
        payload = request.get_json(silent=True)
        if not payload:
            logger.info(f"{user_info} Home URL is required to find DLG URL")
            return jsonify({"status": HTTPStatus.BAD_REQUEST, "message": f"Missing Home URL",
                            "user_info": user_info}), HTTPStatus.BAD_REQUEST

        home_url = payload['home_url']
        if not home_url:
            logger.info(f"{user_info} Home URL is required to find DLG URL")
            return jsonify({"status": HTTPStatus.BAD_REQUEST, "message": f"Missing Home URL",
                            "user_info": user_info}), HTTPStatus.BAD_REQUEST

        logger.info(f"{user_info} Calling find_dlg_url for : {home_url}")
        lsp_service = LSPMasterService(user_claims)
        dlg_url, reason = lsp_service.find_dlg_url(home_url)

        if dlg_url:
            return jsonify({"status": HTTPStatus.OK, "message": f"DLG Url Found for {home_url} after {reason}", "user_info": user_info,
                            "data": {"dlg_url": dlg_url}}), HTTPStatus.OK
        else:
            logger.info(f"{user_info} DLG URL not found for {home_url}")
            return jsonify(
                {"status": HTTPStatus.NOT_FOUND, "message": f'DLG URL Not Found for {home_url} reason: {reason}',
                 "user_info": user_info}), HTTPStatus.NOT_FOUND
    except Exception as exc:
        logger.critical(f"{user_info} Exception finding DLG URL: {str(exc)}", exc_info=True)
        return jsonify(
            {"status": HTTPStatus.INTERNAL_SERVER_ERROR,
             "message": f"Exception finding DLG URL {str(exc)}",
             "user_info": user_info}), HTTPStatus.INTERNAL_SERVER_ERROR


@lsp_master_bp.post("/api/lsp_master")
@token_required
@limiter.limit("10 per minute")
def handle_new_lsp_master():
    """Handle LSP master update request."""
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify(
            {"status": HTTPStatus.BAD_REQUEST, "message": 'No Data found',
             "user_info": user_info}), HTTPStatus.BAD_REQUEST

    try:
        # typecast payload to lspMasterIp
        lsp_master_ip = LspMasterIp(**payload)
        lsp_service = LSPMasterService(user_claims)
        lsp = lsp_service.insert(lsp_master_ip)
        if not lsp:
            message = f"Could not insert New LSP {payload}. LSP already exists"
            logger.error(f"{user_info} {message}")
            return jsonify(
                {"status": HTTPStatus.INTERNAL_SERVER_ERROR, "message": message,
                 "user_info": user_info}), HTTPStatus.INTERNAL_SERVER_ERROR
        else:
            logger.info(f"{user_info} Inserted LSP Master record {lsp_master_ip.lsp_name}")
            return jsonify(
                {"status": HTTPStatus.OK, "message": "LSP data added successfully", "user_info": user_info, "data": lsp,
                 "count": 1}), HTTPStatus.OK
    except Exception as exc:
        logger.critical(f"{user_info} Error inserting LSP master: {str(exc)} {payload}", exc_info=True)
        return jsonify(
            {"status": HTTPStatus.BAD_REQUEST, "message": str(exc), "user_info": user_info}), HTTPStatus.BAD_REQUEST


@lsp_master_bp.put("/api/lsp_master")
@token_required
@limiter.limit("10 per minute")
def handle_update_lsp_master():
    """Handle LSP master update request."""
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify(
            {"status": HTTPStatus.BAD_REQUEST, "message": 'Missing input Payload',
             "user_info": user_info}), HTTPStatus.BAD_REQUEST

    try:
        lsp_master = LspMaster(**payload)
        lsp_service = LSPMasterService(user_claims)
        # if lsp_master.active.lower() == 'true':
        #     lsp_master.active = True
        # else:
        #     lsp_master.active = False
        lsp = lsp_service.update(lsp_master)
        if not lsp:
            logger.warning(f"{user_info} LSP Master record not found for update")
            return jsonify(
                {"status": HTTPStatus.NOT_FOUND, "message": 'LSP Not Found',
                 "user_info": user_info}), HTTPStatus.NOT_FOUND
        logger.info(f"{user_info} Updated LSP Master record with ID {lsp['id']}")
        return jsonify(
            {"status": HTTPStatus.OK, "message": "LSP data updated successfully", "user_info": user_info, "data": lsp,
             "count": 1}), HTTPStatus.OK
    except Exception as exc:
        logger.critical(f"{user_info} Error updating LSP master: {str(exc)}", exc_info=True)
        return jsonify(
            {"status": HTTPStatus.INTERNAL_SERVER_ERROR, "message": str(exc),
             "user_info": user_info}), HTTPStatus.INTERNAL_SERVER_ERROR


@lsp_master_bp.delete("/api/lsp_master")
@token_required
@limiter.limit("10 per minute")
def handle_delete_lsp_master():
    """Handle LSP master delete request."""
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"

    if user_role != 'admin':
        return jsonify(
            {"status": HTTPStatus.UNAUTHORIZED, "message": 'Not Allowed to Delete LSP',
             "user_info": user_info}), HTTPStatus.UNAUTHORIZED

    try:
        lsp_id = request.args.get('lsp_id', default=0, type=int)
        lsp_service = LSPMasterService(user_claims)
        deleted = lsp_service.delete(lsp_id)
        if deleted <= 0:
            logger.warning(f"{user_info} LSP Master record with ID {lsp_id} not found for deletion")
            return jsonify(
                {"status": HTTPStatus.NOT_FOUND, "message": 'LSP Not Found',
                 "user_info": user_info}), HTTPStatus.NOT_FOUND
        logger.info(f"{user_info} Deleted LSP Master record with ID {lsp_id}")
        return jsonify(
            {"status": HTTPStatus.OK, "message": 'LSP Deleted', "user_info": user_info}), HTTPStatus.OK
    except Exception as exc:
        logger.critical(f"{user_info} Error deleting LSP master: {str(exc)}", exc_info=True)
        return jsonify(
            {"status": HTTPStatus.BAD_REQUEST, "message": str(exc), "user_info": user_info}), HTTPStatus.BAD_REQUEST
