from utils.logger_config import logger_method

from DatabaseOperation.DatabaseModels.orm_models import AuditLog
from General.Managers.AuditLogManager import AuditLogManager


class AuditLogService:
    def __init__(self):
        self.logger = logger_method(__name__)
        self.audit_manager = AuditLogManager()

    def record(self, entry: AuditLog) -> AuditLog | None:
        return self.audit_manager.record(entry)
