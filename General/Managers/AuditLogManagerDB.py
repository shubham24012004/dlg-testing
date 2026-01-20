"""
AuditLogManager with DB support for audit logs.
"""
from __future__ import annotations
import datetime as dt
from pathlib import Path
from typing import Iterable, Optional
from sqlalchemy.exc import SQLAlchemyError
from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.SQLAlchemy.DatabaseModels.orm_models import AuditLogORM, AuditAction, Base, LspMasterORM
from DatabaseOperation.SQLAlchemy.DatabaseModels import AuditLog

class AuditLogManagerDB:
    """Audit logger that writes to SQLite via SQLAlchemy ORM."""
    def __init__(self, db_path: str = None):
        self.conn_factory = ConnectionFactory(db_path)
        self.conn_factory.create_all_tables(base=Base)

    def record(self, entry: AuditLog) -> None:
        session = self.conn_factory.get_session()
        try:
            # try to resolve legacy string lsp_id to numeric PK
            resolved_lsp_id = None
            legacy = None
            if entry.lsp_id is not None:
                try:
                    resolved_lsp_id = int(entry.lsp_id)
                except Exception:
                    legacy = entry.lsp_id
                    lm = session.query(LspMasterORM).filter_by(legacy_id=legacy).one_or_none()
                    if lm:
                        resolved_lsp_id = lm.id

            db_entry = AuditLogORM(
                lsp_id=resolved_lsp_id,
                legacy_lsp_id=legacy,
                auto_manual=entry.auto_manual,
                user_id=entry.user_id,
                payload=entry.payload or "",
                action_taken=(entry.action_taken.value if hasattr(entry.action_taken, "value") else entry.action_taken),
            )
            session.add(db_entry)
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            print(f"[AuditLogManagerDB] Error: {e}")
        finally:
            session.close()

    def bulk_record(self, entries: Iterable[AuditLog]) -> None:
        session = self.conn_factory.get_session()
        try:
            for entry in entries:
                resolved_lsp_id = None
                legacy = None
                if entry.lsp_id is not None:
                    try:
                        resolved_lsp_id = int(entry.lsp_id)
                    except Exception:
                        legacy = entry.lsp_id
                        lm = session.query(LspMasterORM).filter_by(legacy_id=legacy).one_or_none()
                        if lm:
                            resolved_lsp_id = lm.id

                db_entry = AuditLogORM(
                    lsp_id=resolved_lsp_id,
                    legacy_lsp_id=legacy,
                    auto_manual=entry.auto_manual,
                    user_id=entry.user_id,
                    payload=entry.payload or "",
                    action_taken=(entry.action_taken.value if hasattr(entry.action_taken, "value") else entry.action_taken),
                )
                session.add(db_entry)
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            print(f"[AuditLogManagerDB] Bulk error: {e}")
        finally:
            session.close()

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
