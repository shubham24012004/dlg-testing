from __future__ import annotations

from typing import Iterable, Optional
import datetime as dt

from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.SQLAlchemy.DatabaseModels.orm_models import LspMasterORM, Base
from DatabaseOperation.SQLAlchemy.DatabaseModels import LspMaster


class LspMasterManagerDB:
    """DB-backed manager for `lsp_master` rows."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.conn_factory = ConnectionFactory(db_path)
        self.conn_factory.create_all_tables(base=Base)

    def upsert(self, lm: LspMaster) -> None:
        session = self.conn_factory.get_session()
        try:
            # Prefer matching by legacy string id if provided, otherwise by name
            legacy = lm.lsp_id or lm.lsp_name
            existing = session.query(LspMasterORM).filter_by(legacy_id=legacy).one_or_none()
            if existing:
                existing.name = lm.lsp_name
                existing.home_url = lm.disclosure_url
                existing.active = lm.is_active
            else:
                row = LspMasterORM(legacy_id=legacy, name=lm.lsp_name, home_url=lm.disclosure_url, active=lm.is_active)
                session.add(row)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def bulk_upsert(self, rows: Iterable[LspMaster]) -> int:
        count = 0
        for r in rows:
            self.upsert(r)
            count += 1
        return count
