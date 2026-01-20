from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Iterable, Optional

from DatabaseOperation.SQLAlchemy.DatabaseModels import AuditAction, AuditLog
from General.Managers.AuditLogManagerDB import AuditLogManagerDB


class AuditLogManager:
    """Trivial audit logger that writes newline-delimited text files."""

    def __init__(self, log_path: str | Path = "logs/audit.log") -> None:
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_manager = AuditLogManagerDB()

    def record(self, entry: AuditLog) -> None:
        payload = (
            f"{entry.created_at.isoformat()} | {entry.lsp_id} | {entry.action_taken.value} | "
            f"{entry.auto_manual} | {entry.user_id} | {entry.payload or '-'}\n"
        )
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(payload)
        self.db_manager.record(entry)

    def bulk_record(self, entries: Iterable[AuditLog]) -> None:
        for entry in entries:
            self.record(entry)

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
