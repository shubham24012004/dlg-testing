"""Controller for DlgRaw add, update, and delete operations."""
from http import HTTPStatus
from flask import Blueprint, request, jsonify
from typing import Any

from utils.logger_config import logger_method
from utils.jwt_utils import token_required
from Service.DlgRawService import DlgRawService
from DatabaseOperation.DatabaseModels.master_models import DlgRawInput, DlgRawUpdate
from utils.rate_limiter import limiter

dlg_raw_bp = Blueprint('dlg_raw_bp', __name__)
logger = logger_method(__name__)

@dlg_raw_bp.post("/api/dlg_raw")
@token_required
@limiter.limit("10 per minute")
def add_dlg_raw() -> Any:
    """Add a new DlgRaw record.

    Request body:
        {
            "lsp_id": 1,
            "lsp_name": "ExampleLSP",
            "lender": "ExampleLender",
            "portfolio": "ExamplePortfolio",
            "amount": 12345.67,
            "as_on_timestamp": "2025-01-31T00:00:00+00:00",
            "scrape_timestamp": "2025-02-01T10:00:00+00:00",
            "complete": "Yes",
            "dlg_url": "https://example.com/dlg"
        }
    """
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"

    if user_role != 'admin':
        return jsonify(
            {"status": HTTPStatus.UNAUTHORIZED, "message": "Not allowed to add DlgRaw records",
             "user_info": user_info}), HTTPStatus.UNAUTHORIZED

    try:
        data = request.get_json(silent=True, force=True)
        if not data:
            logger.info(f"{user_info} Add DlgRaw attempt with no request body")
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": "Request body is required",
                "user_info": user_info
            }), HTTPStatus.BAD_REQUEST

        raw_input = DlgRawInput(**data)

        missing = [f for f in ("lsp_id", "lender", "portfolio", "amount", "as_on_timestamp", "dlg_url")
                   if not getattr(raw_input, f, None)]
        if missing:
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": f"Missing required fields: {', '.join(missing)}",
                "user_info": user_info
            }), HTTPStatus.BAD_REQUEST

        raw_service = DlgRawService(user_claims)
        success, error, result = raw_service.insert(raw_input)

        if not success:
            logger.warning(f"{user_info} Failed to add DlgRaw record: {error}")
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": error,
                "user_info": user_info
            }), HTTPStatus.BAD_REQUEST

        logger.info(f"{user_info} DlgRaw record added for lsp_id={raw_input.lsp_id}")
        return jsonify({
            "status": HTTPStatus.CREATED,
            "message": "DlgRaw record added successfully",
            "user_info": user_info,
            "data": result
        }), HTTPStatus.CREATED

    except Exception as exc:
        logger.critical(f"{user_info} Error adding DlgRaw record: {str(exc)}", exc_info=True)
        return jsonify({
            "status": HTTPStatus.INTERNAL_SERVER_ERROR,
            "message": "Failed to add DlgRaw record",
            "user_info": user_info
        }), HTTPStatus.INTERNAL_SERVER_ERROR


@dlg_raw_bp.put("/api/dlg_raw")
@token_required
@limiter.limit("10 per minute")
def update_dlg_raw() -> Any:
    """Update an existing DlgRaw record.

    Request body:
        {
            "id": 42,
            "lender": "UpdatedLender",
            "amount": 99999.99,
            "complete": "Partial"
        }
    """
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"

    if user_role != 'admin':
        return jsonify(
            {"status": HTTPStatus.UNAUTHORIZED, "message": "Not allowed to update DlgRaw records",
             "user_info": user_info}), HTTPStatus.UNAUTHORIZED

    try:
        data = request.get_json(silent=True, force=True)
        if not data:
            logger.info(f"{user_info} Update DlgRaw attempt with no request body")
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": "Request body is required",
                "user_info": user_info
            }), HTTPStatus.BAD_REQUEST

        raw_update = DlgRawUpdate(**data)

        raw_service = DlgRawService(user_claims)
        success, error, result = raw_service.update(raw_update)

        if not success:
            logger.warning(f"{user_info} Failed to update DlgRaw record id={raw_update.id}: {error}")
            return jsonify({
                "status": HTTPStatus.NOT_FOUND,
                "message": error,
                "user_info": user_info
            }), HTTPStatus.NOT_FOUND

        logger.info(f"{user_info} DlgRaw record id={raw_update.id} updated successfully")
        return jsonify({
            "status": HTTPStatus.OK,
            "message": "DlgRaw record updated successfully",
            "user_info": user_info,
            "data": result
        }), HTTPStatus.OK

    except Exception as exc:
        logger.critical(f"{user_info} Error updating DlgRaw record: {str(exc)}", exc_info=True)
        return jsonify({
            "status": HTTPStatus.INTERNAL_SERVER_ERROR,
            "message": "Failed to update DlgRaw record",
            "user_info": user_info
        }), HTTPStatus.INTERNAL_SERVER_ERROR


@dlg_raw_bp.delete("/api/dlg_raw")
@token_required
@limiter.limit("10 per minute")
def delete_dlg_raw() -> Any:
    """Delete a DlgRaw record by its id.

    Query param:
        id (int): primary key of the DlgRaw record to delete
    """
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"

    if user_role != 'admin':
        return jsonify(
            {"status": HTTPStatus.UNAUTHORIZED, "message": "Not allowed to delete DlgRaw records",
             "user_info": user_info}), HTTPStatus.UNAUTHORIZED

    try:
        raw_id = request.args.get('id', default=0, type=int)
        if not raw_id:
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": "Query parameter 'id' is required",
                "user_info": user_info
            }), HTTPStatus.BAD_REQUEST

        raw_service = DlgRawService(user_claims)
        success, error = raw_service.delete(raw_id)

        if not success:
            logger.warning(f"{user_info} Failed to delete DlgRaw record id={raw_id}: {error}")
            return jsonify({
                "status": HTTPStatus.NOT_FOUND,
                "message": error,
                "user_info": user_info
            }), HTTPStatus.NOT_FOUND

        logger.info(f"{user_info} DlgRaw record id={raw_id} deleted successfully")
        return jsonify({
            "status": HTTPStatus.OK,
            "message": "DlgRaw record deleted successfully",
            "user_info": user_info,
            "data": {"id": raw_id}
        }), HTTPStatus.OK

    except Exception as exc:
        logger.critical(f"{user_info} Error deleting DlgRaw record: {str(exc)}", exc_info=True)
        return jsonify({
            "status": HTTPStatus.INTERNAL_SERVER_ERROR,
            "message": "Failed to delete DlgRaw record",
            "user_info": user_info
        }), HTTPStatus.INTERNAL_SERVER_ERROR
