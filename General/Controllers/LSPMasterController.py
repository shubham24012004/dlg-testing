from typing import Any, Dict, List, Optional, Tuple

from utils.logger_config import logger_method
from flask import Request

from General.Service.LspMasterService import LSPMasterService


class LSPMasterController:
    """Controller for API operations with business logic."""

    def __init__(self):
        self.logger = logger_method(__name__)
        self.lsp_service = LSPMasterService()

    def handle_list_lsp_master(self, request: Request) -> Tuple[Dict[str, Any], int]:
        """Handle LSP master list request."""
        results = self.list_lsp_masters_dict(limit=1000)
        return {"status": "ok", "count": len(results), "rows": results}, 200

    def handle_get_lsp_master(self, lsp_id: int) -> Tuple[Dict[str, Any], int]:
        """Handle get single LSP master request."""
        lsp = self.get_lsp_master_dict(lsp_id)
        if not lsp:
            return {"status": "error", "message": "not found"}, 404
        return {"status": "ok", "lsp": lsp}, 200

    def handle_update_lsp_master(self, id: int, request: Request) -> Tuple[Dict[str, Any], int]:
        """Handle LSP master update request."""
        payload = request.get_json(silent=True)
        if not payload:
            return {"status": "error", "message": "empty payload"}, 400

        try:
            lsp = self.update_lsp_master_dict(id, payload)
            if not lsp:
                return {"status": "error", "message": "not found"}, 404
            return {"status": "ok", "lsp": lsp}, 200
        except Exception as exc:
            self.logger.error("Error updating LSP master: %s", str(exc), exc_info=True)
            return {"status": "error", "message": str(exc)}, 500

    def handle_delete_lsp_master(self, lsp_id: str) -> Tuple[Dict[str, Any], int]:
        """Handle LSP master delete request."""
        try:
            deleted = self.lsp_service.delete(int(lsp_id))
            if not deleted:
                return {"status": "error", "message": "not found"}, 404
            return {"status": "ok", "deleted": lsp_id}, 200
        except Exception as exc:
            self.logger.error("Error deleting LSP master: %s", str(exc), exc_info=True)
            return {"status": "error", "message": str(exc)}, 500

    # ==================== LspMaster Operations ====================

    def get_lsp_master_dict(self, lsp_id: int) -> Optional[Dict[str, Any]]:
        """Get LSP master as dictionary.
        
        Args:
            lsp_id: LSP ID
            
        Returns:
            Dictionary with LSP data or None if not found
        """
        lsp = self.lsp_service.get_lsp_master(lsp_id)
        if not lsp:
            return None
        return {
            "id": lsp.id,
            "name": lsp.name,
            "home_url": lsp.home_url,
            "active": lsp.active,
        }

    def list_lsp_masters_dict(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """List LSP masters as dictionaries.
        
        Args:
            limit: Maximum records to return
            
        Returns:
            List of dictionaries with LSP data
        """
        rows = self.lsp_service.list_lsp_master(limit=limit)
        return [
            {"id": r.id, "name": r.name, "home_url": r.home_url, "active": r.active}
            for r in rows
        ]

    def update_lsp_master_dict(self, id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update LSP master and return as dictionary.
        
        Args:
            id: LSP ID
            data: Dictionary with update fields
            
        Returns:
            Updated LSP dictionary or None if not found
        """
        lsp = self.lsp_service.update(data)
        if not lsp:
            return None
        return lsp


__all__ = ["LSPMasterController"]
