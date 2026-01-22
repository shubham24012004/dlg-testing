from utils.logger_config import logger_method

from DatabaseOperation.DatabaseModels.orm_models import AuditLog
from General.Managers.AuditLogManager import AuditLogManager


class AuditLogService:
    def __init__(self):
        self.logger = logger_method(__name__)
        self.audit_manager = AuditLogManager()

    def record(self, entry: AuditLog) -> AuditLog | None:
        payload = (
            f"{entry.created_at.isoformat()} | {entry.lsp_id} | {entry.action_taken.value} | "
            f"{entry.auto_manual} | {entry.user_id} | {entry.payload or '-'}\n"
        )
        return self.audit_manager.record(entry)
