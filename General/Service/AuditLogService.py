import datetime as dt
from typing import Optional, Any, Dict
from utils.logger_config import logger_method

from DatabaseOperation.DatabaseModels.orm_models import AuditLog, AuditAction
from General.Managers.AuditLogManager import AuditLogManager


class AuditLogService:
    def __init__(self):
        self.logger = logger_method(__name__)
        self.audit_manager = AuditLogManager()

    def record(self, entry: AuditLog) -> bool:
        return self.audit_manager.record(entry)

    def build(self,
              action_taken: AuditAction,
              auto_manual: str,
              user_id: str,
              lsp_id: Optional[str] = None,
              payload: Optional[Any] = None,
              user_claims: Optional[Dict[str, Any]] = None) -> AuditLog:
        return self.audit_manager.build(lsp_id, action_taken, auto_manual, user_id, payload, user_claims)

    def list_audit_logs(self,
                        start_date: Optional[dt.date] = (dt.datetime.now() - dt.timedelta(30)).date(),
                        end_date: Optional[dt.date] = dt.datetime.now().date(),
                        lsp_id: Optional[int] = None,
                        action_str: Optional[str] = None,
                        page: int = 1,
                        page_size: int = 10):
        return self.audit_manager.list_audit_log(start_date=start_date, end_date=end_date, lsp_id=lsp_id,
                                                 action_str=action_str, page=page, page_size=page_size)
