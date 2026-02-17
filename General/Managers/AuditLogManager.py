"""
AuditLogService with DB support for audit logs.
"""
import datetime as dt
import json
from typing import Optional, Any, Dict

from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError
from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.DatabaseModels.master_models import AuditAction, AuditLog
from utils.logger_config import logger_method


class AuditLogManager:
    """Audit logger that writes to SQLite via SQLAlchemy ORM."""

    def __init__(self, user_claims: Optional[Dict[str, Any]] = None):
        self.conn_factory = ConnectionFactory()
        self.user_claims = user_claims
        self.logger = logger_method(__name__)

    def _get_user_info(self) -> str:
        """Get formatted user info string from user_claims."""
        if not self.user_claims:
            return "[User: system, Role: unknown]"
        username = self.user_claims.get('username', 'unknown')
        user_role = self.user_claims.get('role', 'unknown')
        return f"[User: {username}, Role: {user_role}]"

    def record(self, entry: AuditLog) -> bool:
        session = self.conn_factory.get_session()
        try:
            session.add(entry)
            session.commit()
            self.logger.info(f"{self._get_user_info()} Audit log recorded for LSP ID: {entry.lsp_id}")
            return True
        except SQLAlchemyError as e:
            session.rollback()
            self.logger.exception(f"{self._get_user_info()} [AuditLogManagerDB] Error: {e}")
            return False
        finally:
            session.close()

    def build(self,
              lsp_id: str,
              action_taken: AuditAction,
              auto_manual: str,
              user_id: str,
              payload: Optional[Any] = None,
              ) -> AuditLog:
        # Merge user details into payload
        if payload is None:
            payload = {}

        # Add user information to payload
        if self.user_claims:
            payload["user_details"] = {
                "username": self.user_claims.get('username'),
                "user_id_jwt": self.user_claims.get('user_id'),
                "role": self.user_claims.get('role'),
            }

        return AuditLog(
            lsp_id=lsp_id,
            action_taken=action_taken,
            auto_manual=auto_manual,
            user_id=user_id,
            payload=payload,
            log_timestamp=dt.datetime.utcnow(),
        )

    def list_audit_log(self, start_date, end_date, lsp_id, action_str, page, page_size):
        session = self.conn_factory.get_session()
        try:
            query = session.query(AuditLog).order_by(desc(AuditLog.log_timestamp))

            if lsp_id:
                query = query.filter(AuditLog.lsp_id == lsp_id)

            # --- action filter: supports AuditAction or string like "LOGIN" ---
            if action_str:
                action_enum = None
                if isinstance(action_str, AuditAction):
                    action_enum = action_str
                elif isinstance(action_str, str):
                    s = action_str.strip()
                    # Prefer match by Enum NAME, e.g., "LOGIN"
                    try:
                        action_enum = AuditAction[s]
                    except Exception:
                        # Fallback: match by Enum VALUE if caller passes the value
                        try:
                            action_enum = AuditAction(s)
                        except Exception:
                            action_enum = None

                if action_enum:
                    query = query.filter(AuditLog.action_taken == action_enum)

            # --- date filters: convert date -> datetime bounds (recommended) ---
            if start_date:
                if isinstance(start_date, dt.date) and not isinstance(start_date, dt.datetime):
                    start_date = dt.datetime.combine(start_date, dt.time.min)
                query = query.filter(AuditLog.log_timestamp >= start_date)

            if end_date:
                if isinstance(end_date, dt.date) and not isinstance(end_date, dt.datetime):
                    end_date = dt.datetime.combine(end_date, dt.time.max)
                query = query.filter(AuditLog.log_timestamp <= end_date)

            total_count = query.count()

            if page and page_size:
                query = query.offset((page - 1) * page_size).limit(page_size)

            rows = query.all()
            result = []

            for row in rows:
                payload_val = row.payload
                # If payload is stored as JSON dict, keep it. If string, try parse.
                if isinstance(payload_val, str):
                    try:
                        payload_val = json.loads(payload_val)
                    except Exception:
                        payload_val = {"raw": payload_val}

                result.append({
                    "lsp_id": row.lsp_id,
                    "auto_manual": row.auto_manual,
                    "user_id": row.user_id,
                    "payload": payload_val,
                    "action_taken": row.action_taken.value if hasattr(row.action_taken, "value") else str(row.action_taken),
                    "log_timestamp": row.log_timestamp,
                })

            return result, total_count, len(result)

        except SQLAlchemyError as e:
            self.logger.exception(f"{self._get_user_info()} [AuditLogManagerDB] Error: {e}")
        finally:
            session.close()

        return None
