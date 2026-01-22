"""
AuditLogService with DB support for audit logs.
"""
import datetime as dt
from typing import Optional
from sqlalchemy.exc import SQLAlchemyError
from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.DatabaseModels.orm_models import AuditAction, LspMaster, AuditLog
from utils.logger_config import logger_method


class AuditLogManager:
    """Audit logger that writes to SQLite via SQLAlchemy ORM."""

    def __init__(self):
        self.conn_factory = ConnectionFactory()
        self.logger = logger_method(__name__)

    def record(self, entry: AuditLog) -> AuditLog | None:
        session = self.conn_factory.get_session()
        try:
            # try to resolve non-numeric `lsp_id` to numeric PK
            resolved_lsp_id = None
            identifier_str = None
            if entry.lsp_id is not None:
                try:
                    resolved_lsp_id = int(entry.lsp_id)
                except (ValueError, TypeError):
                    identifier_str = entry.lsp_id
                    # try resolving by name (identifier_str may be LSP name)
                    lm = session.query(LspMaster).filter_by(name=identifier_str).one_or_none()
                    if lm:
                        resolved_lsp_id = lm.id

            db_entry = AuditLog(
                lsp_id=resolved_lsp_id,
                auto_manual=entry.auto_manual,
                user_id=entry.user_id,
                payload=entry.payload or "",
                action_taken=(entry.action_taken.value if hasattr(entry.action_taken, "value") else entry.action_taken),
            )
            session.add(db_entry)
            session.commit()
            return db_entry
        except SQLAlchemyError as e:
            session.rollback()
            print(f"[AuditLogManagerDB] Error: {e}")
        finally:
            session.close()
        return None

    @staticmethod
    def build(
            lsp_id: str,
            action_taken: AuditAction,
            auto_manual: str,
            user_id: str,
            payload: Optional[str] = None,
    ) -> AuditLog:
        return AuditLog(
            lsp_id=lsp_id,
            action_taken=action_taken,
            auto_manual=auto_manual,
            user_id=user_id,
            payload=payload,
            created_at=dt.datetime.utcnow(),
        )

    def list_audit_log(self, lsp_id: Optional[int] = None, action_str: Optional[str] = None, limit: int = 1000) -> [
        AuditLog]:
        session = self.conn_factory.get_session()
        try:
            #     ToDo Return list with filters applied
            return None
        except SQLAlchemyError as e:
            session.rollback()
            print(f"[AuditLogManagerDB] Error: {e}")
        finally:
            session.close()
        return None
