"""API Controller for REST endpoints.

Handles all business logic for CRUD operations via Flask routes.
Routes should be thin wrappers that delegate to this controller.

All methods return tuples of (response_dict, status_code) for Flask.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from flask import Request

from DatabaseOperation.SQLAlchemy.DatabaseManager import get_db_manager
from DatabaseOperation.SQLAlchemy.DatabaseModels.orm_models import (
    LspMasterORM,
    DlgCrawlerConfigORM,
    AuditAction,
)
from DatabaseOperation.SQLAlchemy.DatabaseModels import LspMaster as LspMasterDC

logger = logging.getLogger(__name__)


class ApiController:
    """Controller for API operations with business logic."""

    def __init__(self):
        """Initialize controller with singleton DatabaseManager."""
        self.db = get_db_manager()

    # ==================== Flask Request Handlers ====================
    # These methods handle Flask requests and return (response_dict, status_code) tuples

    def handle_upsert_lsp_master(self, request: Request) -> Tuple[Dict[str, Any], int]:
        """Handle LSP master upsert request."""
        payload = request.get_json(silent=True)
        if not payload:
            return {"status": "error", "message": "empty payload"}, 400

        items = payload if isinstance(payload, list) else [payload]
        
        try:
            count = self.upsert_lsp_masters_bulk(items)
            return {"status": "ok", "upserted": count}, 200
        except Exception as exc:
            logger.error("Error upserting LSP masters: %s", str(exc), exc_info=True)
            return {"status": "error", "message": str(exc)}, 500

    def handle_list_lsp_master(self, request: Request) -> Tuple[Dict[str, Any], int]:
        """Handle LSP master list request."""
        results = self.list_lsp_masters_dict(limit=1000)
        return {"status": "ok", "count": len(results), "rows": results}, 200

    def handle_get_lsp_master(self, id: int) -> Tuple[Dict[str, Any], int]:
        """Handle get single LSP master request."""
        lsp = self.get_lsp_master_dict(id)
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
            logger.error("Error updating LSP master: %s", str(exc), exc_info=True)
            return {"status": "error", "message": str(exc)}, 500

    def handle_delete_lsp_master(self, lsp_id: str) -> Tuple[Dict[str, Any], int]:
        """Handle LSP master delete request."""
        try:
            deleted = self.delete_lsp_master_cascade(lsp_id)
            if not deleted:
                return {"status": "error", "message": "not found"}, 404
            return {"status": "ok", "deleted": lsp_id}, 200
        except Exception as exc:
            logger.error("Error deleting LSP master: %s", str(exc), exc_info=True)
            return {"status": "error", "message": str(exc)}, 500

    def handle_upsert_dlg_config(self, request: Request) -> Tuple[Dict[str, Any], int]:
        """Handle DLG crawler config upsert request."""
        payload = request.get_json(silent=True)
        if not payload:
            return {"status": "error", "message": "empty payload"}, 400

        items = payload if isinstance(payload, list) else [payload]
        
        try:
            count = self.upsert_dlg_configs_bulk(items)
            return {"status": "ok", "upserted": count}, 200
        except Exception as exc:
            logger.error("Error upserting DLG configs: %s", str(exc), exc_info=True)
            return {"status": "error", "message": str(exc)}, 500

    def handle_list_dlg_config(self, request: Request) -> Tuple[Dict[str, Any], int]:
        """Handle DLG crawler config list request."""
        results = self.list_dlg_configs_dict(limit=1000)
        return {"status": "ok", "count": len(results), "rows": results}, 200

    def handle_get_dlg_config(self, lsp_id: int) -> Tuple[Dict[str, Any], int]:
        """Handle get single DLG crawler config request."""
        config = self.get_dlg_config_dict(lsp_id)
        if not config:
            return {"status": "error", "message": "not found"}, 404
        return {"status": "ok", "config": config}, 200

    def handle_update_dlg_config(self, lsp_id: int, request: Request) -> Tuple[Dict[str, Any], int]:
        """Handle DLG crawler config update request."""
        payload = request.get_json(silent=True)
        if not payload:
            return {"status": "error", "message": "empty payload"}, 400
        
        try:
            config = self.update_dlg_config_dict(lsp_id, payload)
            if not config:
                return {"status": "error", "message": "not found"}, 404
            return {"status": "ok", "config": config}, 200
        except Exception as exc:
            logger.error("Error updating DLG config: %s", str(exc), exc_info=True)
            return {"status": "error", "message": str(exc)}, 500

    def handle_delete_dlg_config(self, lsp_id: str) -> Tuple[Dict[str, Any], int]:
        """Handle DLG crawler config delete request."""
        try:
            deleted = self.delete_dlg_config_by_lsp(lsp_id)
            if not deleted:
                return {"status": "error", "message": "not found"}, 404
            return {"status": "ok", "deleted": lsp_id}, 200
        except Exception as exc:
            logger.error("Error deleting DLG config: %s", str(exc), exc_info=True)
            return {"status": "error", "message": str(exc)}, 500

    def handle_create_dlg_raw(self, request: Request) -> Tuple[Dict[str, Any], int]:
        """Handle DLG raw create request."""
        payload = request.get_json(silent=True)
        if not payload:
            return {"status": "error", "message": "empty payload"}, 400
        
        items = payload if isinstance(payload, list) else [payload]
        
        try:
            count = self.create_dlg_raw_bulk(items)
            return {"status": "ok", "created": count}, 200
        except ValueError as ve:
            return {"status": "error", "message": str(ve)}, 400
        except Exception as exc:
            logger.error("Error creating DLG raw: %s", str(exc), exc_info=True)
            return {"status": "error", "message": str(exc)}, 500

    def handle_list_dlg_raw(self, request: Request) -> Tuple[Dict[str, Any], int]:
        """Handle DLG raw list request."""
        lsp_id = request.args.get("lsp_id", type=int)
        lsp_name = request.args.get("lsp_name")
        limit = request.args.get("limit", type=int, default=1000)
        
        results = self.list_dlg_raw_dict(lsp_id=lsp_id, lsp_name=lsp_name, limit=limit)
        return {"status": "ok", "count": len(results), "rows": results}, 200

    def handle_create_audit_log(self, request: Request) -> Tuple[Dict[str, Any], int]:
        """Handle audit log create request."""
        payload = request.get_json(silent=True)
        if not payload:
            return {"status": "error", "message": "empty payload"}, 400
        
        try:
            audit = self.create_audit_log_dict(payload)
            return {"status": "ok", "audit": audit}, 200
        except (KeyError, ValueError):
            valid_actions = [a.name for a in AuditAction]
            return {
                "status": "error",
                "message": f"invalid action_taken. Valid values: {valid_actions}"
            }, 400
        except Exception as exc:
            logger.error("Error creating audit log: %s", str(exc), exc_info=True)
            return {"status": "error", "message": str(exc)}, 500

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

    def handle_get_audit_log(self, id: int) -> Tuple[Dict[str, Any], int]:
        """Handle get single audit log request."""
        audit = self.get_audit_log_dict(id)
        if not audit:
            return {"status": "error", "message": "not found"}, 404
        return {"status": "ok", "audit": audit}, 200

    def handle_delete_audit_log(self, id: int) -> Tuple[Dict[str, Any], int]:
        """Handle audit log delete request."""
        try:
            deleted = self.db.delete_audit_log(id)
            if not deleted:
                return {"status": "error", "message": "not found"}, 404
            return {"status": "ok", "deleted": id}, 200
        except Exception as exc:
            logger.error("Error deleting audit log: %s", str(exc), exc_info=True)
            return {"status": "error", "message": str(exc)}, 500

    def handle_trigger_scrape(self, request: Request, crawler_controller) -> Tuple[Dict[str, Any], int]:
        """Handle manual scrape trigger request."""
        payload = request.get_json(silent=True) or {}
        limit = payload.get("limit")
        lsp_id = payload.get("lsp_id")
        
        try:
            crawler_controller.run_scrape(limit=limit, lsp_id=lsp_id)
            return {"status": "ok", "limit": limit, "lsp_id": lsp_id}, 200
        except Exception as exc:
            logger.error("Error triggering scrape: %s", str(exc), exc_info=True)
            return {"status": "error", "message": str(exc)}, 500

    # ==================== LspMaster Operations ====================

    def get_active_sources_for_scraping(self) -> List[LspMasterDC]:
        """Get active LSPs with crawler configs for scraping.
        
        Returns joined data from lsp_master and dlg_crawler_config where both are active.
        """
        with self.db.get_session() as session:
            rows = (
                session.query(LspMasterORM, DlgCrawlerConfigORM)
                .join(DlgCrawlerConfigORM, DlgCrawlerConfigORM.lsp_id == LspMasterORM.id)
                .filter(LspMasterORM.active == True)  # noqa: E712
                .filter(DlgCrawlerConfigORM.is_active == True)  # noqa: E712
                .all()
            )
            
            result: List[LspMasterDC] = []
            for lm, cfg in rows:
                result.append(
                    LspMasterDC(
                        lsp_name=lm.name,
                        disclosure_url=cfg.dlg_url or lm.home_url or "",
                        is_active=bool(lm.active),
                        fetch_hint=cfg.fetch_hint or "auto",
                        parse_hint=cfg.parse_hint or "auto",
                        rules_json=cfg.rules_json,
                        lsp_id=str(lm.id),
                        home_url=lm.home_url,
                        id=lm.id,
                    )
                )
            logger.debug("Retrieved %d active sources for scraping", len(result))
            return result

    def upsert_lsp_masters_bulk(self, items: List[Dict[str, Any]]) -> int:
        """Bulk upsert LSP master records.
        
        Args:
            items: List of dictionaries with LSP data
            
        Returns:
            Count of upserted records
        """
        count = 0
        for item in items:
            self.db.upsert_lsp_master(
                name=item.get("lsp_name") or item.get("name"),
                home_url=item.get("home_url") or item.get("disclosure_url"),
                active=bool(item.get("is_active", True)),
                lsp_id=item.get("lsp_id") or item.get("id"),
            )
            count += 1
        logger.info("Bulk upserted %d LSP master records", count)
        return count

    def get_lsp_master_dict(self, id: int) -> Optional[Dict[str, Any]]:
        """Get LSP master as dictionary.
        
        Args:
            id: LSP ID
            
        Returns:
            Dictionary with LSP data or None if not found
        """
        lsp = self.db.get_lsp_master(id)
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
        rows = self.db.list_lsp_master(limit=limit)
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
        lsp = self.db.update_lsp_master(
            id=id,
            name=data.get("name"),
            home_url=data.get("home_url"),
            active=data.get("active"),
        )
        if not lsp:
            return None
        return {
            "id": lsp.id,
            "name": lsp.name,
            "home_url": lsp.home_url,
            "active": lsp.active,
        }

    def delete_lsp_master_cascade(self, lsp_id: str) -> bool:
        """Delete LSP and its crawler config.
        
        Args:
            lsp_id: LSP ID (numeric or name)
            
        Returns:
            True if deleted, False if not found
        """
        # Find LSP by ID or name
        lm = None
        try:
            int_id = int(lsp_id)
            lm = self.db.get_lsp_master(int_id)
        except Exception:
            lm = self.db.get_lsp_master_by_name(lsp_id)
        
        if not lm:
            return False
        
        # Delete config first (if exists)
        self.db.delete_dlg_crawler_config(lm.id)
        # Delete LSP
        deleted = self.db.delete_lsp_master(lm.id)
        
        if deleted:
            logger.info("Deleted LSP and config: lsp_id=%s", lsp_id)
        return deleted

    # ==================== DlgCrawlerConfig Operations ====================

    def upsert_dlg_configs_bulk(self, items: List[Dict[str, Any]]) -> int:
        """Bulk upsert DLG crawler configs.
        
        Args:
            items: List of dictionaries with config data
            
        Returns:
            Count of upserted records
        """
        count = 0
        for item in items:
            lsp_id = item.get("lsp_id") or item.get("id")
            if not lsp_id:
                raise ValueError("lsp_id required for config upsert")
            
            dlg_url = item.get("dlg_url") or item.get("disclosure_url") or ""
            self.db.upsert_dlg_crawler_config(
                lsp_id=int(lsp_id),
                dlg_url=dlg_url,
                is_active=bool(item.get("is_active", True)),
                fetch_hint=item.get("fetch_hint", "auto"),
                parse_hint=item.get("parse_hint", "auto"),
                rules_json=item.get("rules_json"),
            )
            count += 1
        logger.info("Bulk upserted %d DLG crawler configs", count)
        return count

    def get_dlg_config_dict(self, lsp_id: int) -> Optional[Dict[str, Any]]:
        """Get DLG crawler config as dictionary.
        
        Args:
            lsp_id: LSP ID
            
        Returns:
            Dictionary with config data or None if not found
        """
        config = self.db.get_dlg_crawler_config(lsp_id)
        if not config:
            return None
        return {
            "lsp_id": config.lsp_id,
            "dlg_url": config.dlg_url,
            "is_active": config.is_active,
            "parse_hint": config.parse_hint,
            "fetch_hint": config.fetch_hint,
            "rules_json": config.rules_json,
            "last_crawl_date": config.last_crawl_date.isoformat() if config.last_crawl_date else None,
        }

    def list_dlg_configs_dict(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """List DLG crawler configs as dictionaries.
        
        Args:
            limit: Maximum records to return
            
        Returns:
            List of dictionaries with config data
        """
        rows = self.db.list_dlg_crawler_config(limit=limit)
        return [
            {
                "lsp_id": r.lsp_id,
                "dlg_url": r.dlg_url,
                "is_active": r.is_active,
                "fetch_hint": r.fetch_hint,
                "parse_hint": r.parse_hint,
                "rules_json": r.rules_json,
            }
            for r in rows
        ]

    def update_dlg_config_dict(self, lsp_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update DLG crawler config and return as dictionary.
        
        Args:
            lsp_id: LSP ID
            data: Dictionary with update fields
            
        Returns:
            Updated config dictionary or None if not found
        """
        config = self.db.update_dlg_crawler_config(
            lsp_id=lsp_id,
            dlg_url=data.get("dlg_url"),
            is_active=data.get("is_active"),
            parse_hint=data.get("parse_hint"),
            fetch_hint=data.get("fetch_hint"),
            rules_json=data.get("rules_json"),
        )
        if not config:
            return None
        return {
            "lsp_id": config.lsp_id,
            "dlg_url": config.dlg_url,
            "is_active": config.is_active,
            "parse_hint": config.parse_hint,
            "fetch_hint": config.fetch_hint,
            "rules_json": config.rules_json,
        }

    def delete_dlg_config_by_lsp(self, lsp_id: str) -> bool:
        """Delete DLG crawler config by LSP ID or name.
        
        Args:
            lsp_id: LSP ID (numeric or name)
            
        Returns:
            True if deleted, False if not found
        """
        config_lsp_id = None
        try:
            config_lsp_id = int(lsp_id)
        except Exception:
            lm = self.db.get_lsp_master_by_name(lsp_id)
            if not lm:
                return False
            config_lsp_id = lm.id
        
        deleted = self.db.delete_dlg_crawler_config(config_lsp_id)
        if deleted:
            logger.info("Deleted DLG config: lsp_id=%s", lsp_id)
        return deleted

    # ==================== DlgRaw Operations ====================

    def create_dlg_raw_bulk(self, items: List[Dict[str, Any]]) -> int:
        """Bulk create DLG raw records.
        
        Args:
            items: List of dictionaries with raw data
            
        Returns:
            Count of created records
            
        Raises:
            ValueError: If required fields are missing
        """
        count = 0
        required = ["lsp_id", "lsp_name", "lender", "portfolio", "as_on_timestamp", "scrape_timestamp"]
        
        for item in items:
            missing = [f for f in required if f not in item]
            if missing:
                raise ValueError(f"Missing required fields: {missing}")
            
            self.db.create_dlg_raw(
                lsp_id=item["lsp_id"],
                lsp_name=item["lsp_name"],
                lender=item["lender"],
                portfolio=item["portfolio"],
                as_on_timestamp=item["as_on_timestamp"],
                scrape_timestamp=item["scrape_timestamp"],
                amount=item.get("amount"),
                complete=item.get("complete"),
            )
            count += 1
        
        logger.info("Created %d DLG raw records", count)
        return count

    def list_dlg_raw_dict(
        self, lsp_id: Optional[int] = None, lsp_name: Optional[str] = None, limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """List DLG raw records as dictionaries.
        
        Args:
            lsp_id: Filter by LSP ID (optional)
            lsp_name: Filter by LSP name (optional)
            limit: Maximum records to return
            
        Returns:
            List of dictionaries with raw data
        """
        rows = self.db.list_dlg_raw(lsp_id=lsp_id, lsp_name=lsp_name, limit=limit)
        return [
            {
                "lsp_id": r.lsp_id,
                "lsp_name": r.lsp_name,
                "lender": r.lender,
                "portfolio": r.portfolio,
                "amount": r.amount,
                "as_on_timestamp": r.as_on_timestamp.isoformat() if r.as_on_timestamp else None,
                "scrape_timestamp": r.scrape_timestamp.isoformat() if r.scrape_timestamp else None,
                "complete": r.complete,
            }
            for r in rows
        ]

    # ==================== AuditLog Operations ====================

    def create_audit_log_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create audit log and return as dictionary.
        
        Args:
            data: Dictionary with audit log data
            
        Returns:
            Dictionary with created audit log
            
        Raises:
            KeyError: If action_taken is invalid
        """
        action_str = data.get("action_taken")
        if not action_str:
            raise ValueError("action_taken required")
        
        # Convert string to AuditAction enum
        action = AuditAction[action_str] if isinstance(action_str, str) else action_str
        
        audit = self.db.create_audit_log(
            action_taken=action,
            lsp_id=data.get("lsp_id"),
            auto_manual=data.get("auto_manual"),
            user_id=data.get("user_id"),
            payload=data.get("payload"),
        )
        
        logger.info("Created audit log: id=%d action=%s", audit.id, action.value)
        return {
            "id": audit.id,
            "lsp_id": audit.lsp_id,
            "action_taken": audit.action_taken.value,
            "auto_manual": audit.auto_manual,
            "user_id": audit.user_id,
        }

    def get_audit_log_dict(self, id: int) -> Optional[Dict[str, Any]]:
        """Get audit log as dictionary.
        
        Args:
            id: Audit log ID
            
        Returns:
            Dictionary with audit log data or None if not found
        """
        audit = self.db.get_audit_log(id)
        if not audit:
            return None
        return {
            "id": audit.id,
            "lsp_id": audit.lsp_id,
            "action_taken": audit.action_taken.value,
            "auto_manual": audit.auto_manual,
            "user_id": audit.user_id,
            "payload": audit.payload,
        }

    def list_audit_log_dict(
        self, lsp_id: Optional[int] = None, action_str: Optional[str] = None, limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """List audit logs as dictionaries.
        
        Args:
            lsp_id: Filter by LSP ID (optional)
            action_str: Filter by action name (optional)
            limit: Maximum records to return
            
        Returns:
            List of dictionaries with audit log data
            
        Raises:
            KeyError: If action_str is invalid
        """
        action = None
        if action_str:
            action = AuditAction[action_str]
        
        rows = self.db.list_audit_log(lsp_id=lsp_id, action=action, limit=limit)
        return [
            {
                "id": r.id,
                "lsp_id": r.lsp_id,
                "action_taken": r.action_taken.value,
                "auto_manual": r.auto_manual,
                "user_id": r.user_id,
                "payload": r.payload,
            }
            for r in rows
        ]


__all__ = ["ApiController"]
