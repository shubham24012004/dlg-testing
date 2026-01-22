from typing import Any, Dict, List, Optional, Tuple

from DatabaseOperation.DatabaseModels.orm_models import AuditAction, AuditLog
from utils.logger_config import logger_method
from flask import Request

from General.Service.AuditLogService import AuditLogService


class AuditLogController:
    """Controller for API operations with business logic."""

    def __init__(self):
        self.logger = logger_method(__name__)
        self.audit_service = AuditLogService()

    def handle_list_audit_log(self, request: Request) -> Tuple[Dict[str, Any], int]:
        """Handle audit log list request."""
        lsp_id = request.args.get("lsp_id", type=int)
        action_str = request.args.get("action")
        limit = request.args.get("limit", type=int, default=1000)

        try:
            results = self.list_audit_log_dict(lsp_id=lsp_id, action_str=action_str, limit=limit)
            return {"status": "ok", "count": len(results), "rows": results}, 200
        except KeyError:
            valid_actions = [a.name for a in AuditAction]
            return {
                "status": "error",
                "message": f"invalid action. Valid values: {valid_actions}"
            }, 400


__all__ = ["AuditLogController"]