from http import HTTPStatus
from utils.logger_config import logger_method
from flask import request, jsonify, Blueprint

from General.Service.LspMasterService import LSPMasterService
from DatabaseOperation.DatabaseModels.orm_models import LspMasterIp, LspMaster

"""Controller for API operations with business logic."""

lsp_master_bp = Blueprint('lsp_master_bp', __name__)

logger = logger_method(__name__)
lsp_service = LSPMasterService()


@lsp_master_bp.get("/api/lsp_master")
def handle_list_lsp_master():
    """Handle LSP master list request."""
    try:
        active = request.args.get('active', default=True, type=bool)
        page = request.args.get('page', default=1, type=int)
        per_page = request.args.get('per_page', default=10, type=int)
        lsp_id = request.args.get('lsp_id', default=0, type=int)
        lsp_name = request.args.get('lsp_name', default="", type=str)

        results, rows = lsp_service.list_lsp_master(active_only=active, page=page, per_page=per_page, lsp_id=lsp_id,
                                                    lsp_name=lsp_name)
        logger.info(f"Fetched LSP Master records: {rows}")
        if rows > 0:
            return jsonify({"statusCode": HTTPStatus.OK, "message": "LSP fetched successfully", "data": results,
                            "count": rows})
        else:
            logger.info(f"LSP Master record not found")
            return jsonify(
                {"statusCode": HTTPStatus.NOT_FOUND, "message": 'LSP Not Found'})
    except Exception as exc:
        logger.critical(f"Error listing LSP Master records: {str(exc)}", exc_info=True)
        return jsonify(
            {"statusCode": HTTPStatus.INTERNAL_SERVER_ERROR, "message": str(exc)})


@lsp_master_bp.post("/api/lsp_master")
def handle_new_lsp_master():
    """Handle LSP master update request."""
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify(
            {"statusCode": HTTPStatus.BAD_REQUEST, "message": 'No Data found'})

    try:
        # typecast payload to lspMasterIp
        lsp_master_ip = LspMasterIp(**payload)
        lsp = lsp_service.insert(lsp_master_ip)
        if not lsp:
            message = f"Could not insert New LSP {payload}. LSP already exists"
            logger.error(message)
            return jsonify(
                {"statusCode": HTTPStatus.INTERNAL_SERVER_ERROR, "message": message})
        else:
            # todo
            # if lsp.dlg_url:
            #     in return message show value to user for confirming
            # else"
            #     in return message inform dlg not found
            logger.info(f"Inserted LSP Master record {lsp_master_ip.lsp_name}")
            return jsonify(
                {"statusCode": HTTPStatus.OK, "message": "LSP data added successfully", "data": lsp, "count": 1})
    except Exception as exc:
        logger.critical(f"Error inserting LSP master: {str(exc)} {payload}", exc_info=True)
        return jsonify(
            {"statusCode": HTTPStatus.BAD_REQUEST, "message": str(exc)})


@lsp_master_bp.put("/api/lsp_master/")
def handle_update_lsp_master():
    """Handle LSP master update request."""
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify(
            {"statusCode": HTTPStatus.BAD_REQUEST, "message": 'Missing input Payload'})

    try:
        lsp_master = LspMaster(**payload)
        lsp = lsp_service.update(lsp_master)
        if not lsp:
            logger.warning(f"LSP Master record not found for update")
            return jsonify(
                {"statusCode": HTTPStatus.NOT_FOUND, "message": 'LSP Not Found'})
        logger.info(f"Updated LSP Master record with ID {lsp.id}")
        return jsonify(
            {"statusCode": HTTPStatus.OK, "message": "LSP data updated successfully", "data": lsp, "count": 1})
    except Exception as exc:
        logger.critical(f"Error updating LSP master: {str(exc)}", exc_info=True)
        return jsonify(
            {"statusCode": HTTPStatus.BAD_REQUEST, "message": str(exc)})


@lsp_master_bp.delete("/api/lsp_master/")
def handle_delete_lsp_master():
    """Handle LSP master delete request."""
    try:
        lsp_id = request.args.get('lsp_id', default=0, type=int)
        deleted = lsp_service.delete(lsp_id)
        if deleted <= 0:
            logger.warning(f"LSP Master record with ID {lsp_id} not found for deletion")
            return jsonify(
                {"statusCode": HTTPStatus.NOT_FOUND, "message": 'LSP Not Found'})
        logger.info(f"Deleted LSP Master record with ID {lsp_id}")
        return jsonify(
            {"statusCode": HTTPStatus.OK, "message": 'LSP Deleted'})
    except Exception as exc:
        logger.critical(f"Error deleting LSP master: {str(exc)}", exc_info=True)
        return jsonify(
            {"statusCode": HTTPStatus.BAD_REQUEST, "message": str(exc)})
