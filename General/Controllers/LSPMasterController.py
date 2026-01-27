from http import HTTPStatus
from utils.logger_config import logger_method
from utils.jwt_utils import token_required
from flask import request, jsonify, Blueprint

from General.Service.LspMasterService import LSPMasterService
from DatabaseOperation.DatabaseModels.orm_models import LspMasterIp, LspMaster

"""Controller for API operations with business logic."""

lsp_master_bp = Blueprint('lsp_master_bp', __name__)

logger = logger_method(__name__)
lsp_service = LSPMasterService()


@lsp_master_bp.get("/api/lsp_master")
@token_required
def handle_list_lsp_master():
    """Handle LSP master list request."""
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"
    try:
        active = request.args.get('active', default=True, type=bool)
        page = request.args.get('page', default=1, type=int)
        per_page = request.args.get('per_page', default=10, type=int)
        lsp_id = request.args.get('lsp_id', default=0, type=int)
        lsp_name = request.args.get('lsp_name', default="", type=str)

        results, rows = lsp_service.list_lsp_master(active_only=active, page=page, per_page=per_page, lsp_id=lsp_id,
                                                    lsp_name=lsp_name)
        logger.info(f"{user_info} Fetched LSP Master records: {rows}")
        if rows > 0:
            return jsonify({"status": HTTPStatus.OK, "message": "LSP fetched successfully", "user_info": user_info, "data": results,
                            "count": rows}), HTTPStatus.OK
        else:
            logger.info(f"{user_info} LSP Master record not found")
            return jsonify(
                {"status": HTTPStatus.NOT_FOUND, "message": 'LSP Not Found', "user_info": user_info}), HTTPStatus.NOT_FOUND
    except Exception as exc:
        logger.critical(f"{user_info} Error listing LSP Master records: {str(exc)}", exc_info=True)
        return jsonify(
            {"status": HTTPStatus.INTERNAL_SERVER_ERROR, "message": str(exc), "user_info": user_info}), HTTPStatus.INTERNAL_SERVER_ERROR


@lsp_master_bp.get("/api/get_dlg_url")
@token_required
def get_dlg_url():
    """Handle LSP master list request."""
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"
    try:
        lsp_id = request.args.get('lsp_id', default=0, type=int)
        logger.info(f"{user_info} Calling find_dlg_url for LSP : {lsp_id}")
        lsp_name, dlg_url, reason = lsp_service.find_dlg_url(lsp_id, user_claims=user_claims)

        if dlg_url:
            return jsonify({"status": HTTPStatus.OK, "message": "DLG Url Found", "user_info": user_info, "data": dlg_url}), HTTPStatus.OK
        else:
            logger.info(f"{user_info} DLG URL not found for {lsp_name}")
            return jsonify(
                {"status": HTTPStatus.NOT_FOUND, "message": f'DLG URL Not Found for {lsp_name}', "user_info": user_info}), HTTPStatus.NOT_FOUND
    except Exception as exc:
        logger.critical(f"{user_info} Exception finding DLG URL: {str(exc)}", exc_info=True)
        return jsonify(
            {"status": HTTPStatus.INTERNAL_SERVER_ERROR,
             "message": f"Exception finding DLG URL {str(exc)}", "user_info": user_info}), HTTPStatus.INTERNAL_SERVER_ERROR


@lsp_master_bp.post("/api/lsp_master")
@token_required
def handle_new_lsp_master():
    """Handle LSP master update request."""
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify(
            {"status": HTTPStatus.BAD_REQUEST, "message": 'No Data found', "user_info": user_info}), HTTPStatus.BAD_REQUEST

    try:
        # typecast payload to lspMasterIp
        lsp_master_ip = LspMasterIp(**payload)
        lsp = lsp_service.insert(lsp_master_ip, user_claims=user_claims)
        if not lsp:
            message = f"Could not insert New LSP {payload}. LSP already exists"
            logger.error(f"{user_info} {message}")
            return jsonify(
                {"status": HTTPStatus.INTERNAL_SERVER_ERROR, "message": message, "user_info": user_info}), HTTPStatus.INTERNAL_SERVER_ERROR
        else:
            logger.info(f"{user_info} Inserted LSP Master record {lsp_master_ip.lsp_name}")
            return jsonify(
                {"status": HTTPStatus.OK, "message": "LSP data added successfully", "user_info": user_info, "data": lsp,
                 "count": 1}), HTTPStatus.OK
    except Exception as exc:
        logger.critical(f"{user_info} Error inserting LSP master: {str(exc)} {payload}", exc_info=True)
        return jsonify(
            {"status": HTTPStatus.BAD_REQUEST, "message": str(exc), "user_info": user_info}), HTTPStatus.BAD_REQUEST


@lsp_master_bp.put("/api/lsp_master/")
@token_required
def handle_update_lsp_master():
    """Handle LSP master update request."""
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify(
            {"status": HTTPStatus.BAD_REQUEST, "message": 'Missing input Payload', "user_info": user_info}), HTTPStatus.BAD_REQUEST

    try:
        lsp_master = LspMaster(**payload)
        lsp = lsp_service.update(lsp_master, user_claims=user_claims)
        if not lsp:
            logger.warning(f"{user_info} LSP Master record not found for update")
            return jsonify(
                {"status": HTTPStatus.NOT_FOUND, "message": 'LSP Not Found', "user_info": user_info}), HTTPStatus.NOT_FOUND
        logger.info(f"{user_info} Updated LSP Master record with ID {lsp.id}")
        return jsonify(
            {"status": HTTPStatus.OK, "message": "LSP data updated successfully", "user_info": user_info, "data": lsp,
             "count": 1}), HTTPStatus.OK
    except Exception as exc:
        logger.critical(f"{user_info} Error updating LSP master: {str(exc)}", exc_info=True)
        return jsonify(
            {"status": HTTPStatus.INTERNAL_SERVER_ERROR, "message": str(exc), "user_info": user_info}), HTTPStatus.INTERNAL_SERVER_ERROR


@lsp_master_bp.delete("/api/lsp_master/")
@token_required
def handle_delete_lsp_master():
    """Handle LSP master delete request."""
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"
    try:
        lsp_id = request.args.get('lsp_id', default=0, type=int)
        deleted = lsp_service.delete(lsp_id, user_claims=user_claims)
        if deleted <= 0:
            logger.warning(f"{user_info} LSP Master record with ID {lsp_id} not found for deletion")
            return jsonify(
                {"status": HTTPStatus.NOT_FOUND, "message": 'LSP Not Found', "user_info": user_info}), HTTPStatus.NOT_FOUND
        logger.info(f"{user_info} Deleted LSP Master record with ID {lsp_id}")
        return jsonify(
            {"status": HTTPStatus.OK, "message": 'LSP Deleted', "user_info": user_info}), HTTPStatus.OK
    except Exception as exc:
        logger.critical(f"{user_info} Error deleting LSP master: {str(exc)}", exc_info=True)
        return jsonify(
            {"status": HTTPStatus.BAD_REQUEST, "message": str(exc), "user_info": user_info}), HTTPStatus.BAD_REQUEST
