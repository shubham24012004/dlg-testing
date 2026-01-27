"""
AuditLogService with DB support for audit logs.
"""
import datetime as dt
import json
from typing import Optional, Any, Dict

from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError
from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.DatabaseModels.orm_models import AuditAction, AuditLog
from utils.logger_config import logger_method


class AuditLogManager:
    """Audit logger that writes to SQLite via SQLAlchemy ORM."""

    def __init__(self):
        self.conn_factory = ConnectionFactory()
        self.logger = logger_method(__name__)

    def record(self, entry: AuditLog) -> bool:
        session = self.conn_factory.get_session()
        try:
            db_entry = AuditLog(
                lsp_id=entry.lsp_id,
                auto_manual=entry.auto_manual,
                user_id=entry.user_id,
                payload=entry.payload or "",
                action_taken=entry.action_taken,
                log_timestamp=entry.log_timestamp)
            session.add(db_entry)
            session.commit()
            return True
        except SQLAlchemyError as e:
            session.rollback()
            self.logger.exception(f"[AuditLogManagerDB] Error: {e}")
        finally:
            session.close()
        return False

    @staticmethod
    def build(
            lsp_id: str,
            action_taken: AuditAction,
            auto_manual: str,
            user_id: str,
            payload: Optional[Any] = None,
            user_claims: Optional[Dict[str, Any]] = None,
    ) -> AuditLog:
        # Merge user details into payload
        if payload is None:
            payload = {}

        # Add user information to payload
        if user_claims:
            payload["user_details"] = {
                "username": user_claims.get('username'),
                "user_id_jwt": user_claims.get('user_id'),
                "role": user_claims.get('role'),
            }
        
        return AuditLog(
            lsp_id=lsp_id,
            action_taken=action_taken,
            auto_manual=auto_manual,
            user_id=user_id,
            payload=json.dumps(payload),
            log_timestamp=dt.datetime.utcnow(),
        )

    def list_audit_log(self, start_date, end_date, lsp_id, action_str, page, page_size):
        session = self.conn_factory.get_session()
        try:
            query = session.query(AuditLog).order_by(desc(AuditLog.log_timestamp))
            if lsp_id:
                query = query.filter_by(lsp_id=lsp_id)
            if action_str:
                query = query.filter_by(action_taken=action_str.value)
            if start_date:
                query = query.filter(AuditLog.log_timestamp >= start_date)
            if end_date:
                query = query.filter(AuditLog.log_timestamp <= end_date)
            if page:
                query = query.offset((page - 1) * page_size)
            if page_size:
                query = query.limit(page_size)
            rows = query.all()
            result = []
            for row in rows:
                result_dict = {"lsp_id": row.lsp_id, "auto_manual": row.auto_manual, "user_id": row.user_id,
                               "payload": json.loads(row.payload),
                               "action_taken": row.action_taken.value, "log_timestamp": row.log_timestamp}
                result.append(result_dict)
            return result, len(result)
        except SQLAlchemyError as e:
            self.logger.exception(f"[AuditLogManagerDB] Error: {e}")
        finally:
            session.close()
        return None
