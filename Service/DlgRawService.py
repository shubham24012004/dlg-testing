"""
DlgRawService for add, update, and delete of DlgRaw records.
"""
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, Any

from utils.logger_config import logger_method
from utils.constants import AuditAction, CrawlStatus
from utils.utils import get_month_window
from Managers.DlgRawManager import DlgRawManager
from Managers.LspMasterManager import LspMasterManager
from Service.AuditLogService import AuditLogService
from DatabaseOperation.DatabaseModels.master_models import DlgRawInput, DlgRawUpdate


class DlgRawService:
    """Service layer for DlgRaw CRUD operations."""

    def __init__(self, user_claims: Optional[Dict[str, Any]] = None):
        self.logger = logger_method(__name__)
        self.user_claims = user_claims
        self.raw_manager = DlgRawManager(user_claims)
        self.lsp_manager = LspMasterManager(user_claims)
        self.auditlog_service = AuditLogService(user_claims)

    def insert(self, raw_input: DlgRawInput) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Add a new DlgRaw record.

        Returns:
            Tuple of (success, error_message, created_record)
        """
        try:
            # Fetch lsp_name from lsp_master by lsp_id
            lsp_records, _, _ = self.lsp_manager.list_lsp_master(active_only=True, lsp_id=raw_input.lsp_id)
            if not lsp_records:
                raise Exception(f"LSP with id={raw_input.lsp_id} not found or inactive")
            lsp = lsp_records[0]
            raw_input.lsp_name = lsp["name"]
            raw_input.scrape_timestamp = f"{datetime.now(tz=timezone.utc)}"

            # Compute status based on field values and temporal freshness
            if raw_input.portfolio is None or raw_input.amount is None:
                raw_input.complete = CrawlStatus.PARTIAL.value
            elif raw_input.as_on_timestamp is None:
                raw_input.complete = CrawlStatus.STALE.value
            else:
                window = get_month_window(raw_input.scrape_timestamp)
                if window:
                    win_year, win_month = window
                    exp_year = win_year - 1 if win_month == 1 else win_year
                    exp_month = 12 if win_month == 1 else win_month - 1
                    ason = raw_input.as_on_timestamp
                    if isinstance(ason, str):
                        ason = datetime.fromisoformat(ason)
                    if ason.year != exp_year or ason.month != exp_month:
                        raw_input.complete = CrawlStatus.STALE.value
                    else:
                        raw_input.complete = CrawlStatus.COMPLETED.value
                else:
                    raw_input.complete = CrawlStatus.COMPLETED.value

            result = self.raw_manager.insert(raw_input)
            user_id = self.user_claims.get('username') if self.user_claims else "system"

            if not result:
                error_msg = f"DlgRaw record already exists for lsp_id={raw_input.lsp_id}"
                self.auditlog_service.record(
                    self.auditlog_service.build(
                        lsp_id=f"{raw_input.lsp_id}",
                        action_taken=AuditAction.INSERT_DLG_RAW,
                        auto_manual="manual",
                        user_id=user_id,
                        payload={"status": "Failed", "details": error_msg,
                                 "request_object": raw_input.__dict__}
                    )
                )
                return False, error_msg, None

            self.auditlog_service.record(
                self.auditlog_service.build(
                    lsp_id=f"{raw_input.lsp_id}",
                    action_taken=AuditAction.INSERT_DLG_RAW,
                    auto_manual="manual",
                    user_id=user_id,
                    payload={"status": "Success", "details": "DlgRaw record added", "request_object": result}
                )
            )
            self.logger.info(f"DlgRaw record added for lsp_id={raw_input.lsp_id}")
            return True, None, result
        except Exception as ex:
            user_id = self.user_claims.get('username') if self.user_claims else "system"
            self.auditlog_service.record(
                self.auditlog_service.build(
                    lsp_id=f"{raw_input.lsp_id}",
                    action_taken=AuditAction.INSERT_DLG_RAW,
                    auto_manual="manual",
                    user_id=user_id,
                    payload={"status": "Exception", "details": str(ex), "request_object": raw_input.__dict__}
                )
            )
            self.logger.error(f"Error inserting DlgRaw record: {str(ex)}")
            raise ex

    def update(self, raw_update: DlgRawUpdate) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Update an existing DlgRaw record.

        Returns:
            Tuple of (success, error_message, updated_record)
        """
        try:
            result = self.raw_manager.update(raw_update)
            user_id = self.user_claims.get('username') if self.user_claims else "system"

            if not result:
                error_msg = f"DlgRaw record with id={raw_update.id} not found"
                self.auditlog_service.record(
                    self.auditlog_service.build(
                        lsp_id=raw_update.lsp_id,
                        action_taken=AuditAction.UPDATE_DLG_RAW,
                        auto_manual="manual",
                        user_id=user_id,
                        payload={"status": "Failed", "details": error_msg,
                                 "request_object": {"id": raw_update.id}}
                    )
                )
                return False, error_msg, None

            self.auditlog_service.record(
                self.auditlog_service.build(
                    lsp_id=result["lsp_id"],
                    action_taken=AuditAction.UPDATE_DLG_RAW,
                    auto_manual="manual",
                    user_id=user_id,
                    payload={"status": "Success", "details": "DlgRaw record updated", "request_object": result}
                )
            )
            self.logger.info(f"DlgRaw record id={raw_update.id} updated successfully")
            return True, None, result
        except Exception as ex:
            user_id = self.user_claims.get('username') if self.user_claims else "system"
            self.auditlog_service.record(
                self.auditlog_service.build(
                    lsp_id=raw_update.lsp_id,
                    action_taken=AuditAction.UPDATE_DLG_RAW,
                    auto_manual="manual",
                    user_id=user_id,
                    payload={"status": "Exception", "details": str(ex),
                             "request_object": {"id": raw_update.id, "details": raw_update.__dict__}}
                )
            )
            self.logger.error(f"Error updating DlgRaw record id={raw_update.id}: {str(ex)}")
            raise ex

    def delete(self, raw_id: int) -> Tuple[bool, Optional[str]]:
        """Delete a DlgRaw record by its id.

        Returns:
            Tuple of (success, error_message)
        """
        try:
            result = self.raw_manager.delete(raw_id)
            user_id = self.user_claims.get('username') if self.user_claims else "system"

            if not result:
                error_msg = f"DlgRaw record with id={raw_id} not found"
                self.auditlog_service.record(
                    self.auditlog_service.build(
                        lsp_id=None,
                        action_taken=AuditAction.DELETE_DLG_RAW,
                        auto_manual="manual",
                        user_id=user_id,
                        payload={"status": "Failed", "details": error_msg,
                                 "request_object": {"id": raw_id}}
                    )
                )
                return False, error_msg

            self.auditlog_service.record(
                self.auditlog_service.build(
                    lsp_id=result["lsp_id"],
                    action_taken=AuditAction.DELETE_DLG_RAW,
                    auto_manual="manual",
                    user_id=user_id,
                    payload={"status": "Success", "details": "DlgRaw record deleted",
                             "request_object": {"id": raw_id, "lsp_id": result["lsp_id"]}}
                )
            )
            self.logger.info(f"DlgRaw record id={raw_id} deleted successfully")
            return True, None
        except Exception as ex:
            user_id = self.user_claims.get('username') if self.user_claims else "system"
            self.auditlog_service.record(
                self.auditlog_service.build(
                    lsp_id=None,
                    action_taken=AuditAction.DELETE_DLG_RAW,
                    auto_manual="manual",
                    user_id=user_id,
                    payload={"status": "Exception", "details": str(ex), "request_object": {"id": raw_id}}
                )
            )
            self.logger.error(f"Error deleting DlgRaw record id={raw_id}: {str(ex)}")
            raise ex
