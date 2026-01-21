from __future__ import annotations

from typing import List

from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.SQLAlchemy.DatabaseModels.orm_models import LspMasterORM, Base
from DatabaseOperation.SQLAlchemy.DatabaseModels import LspMaster


class LspMasterManager:
    """Loads and filters ``lsp_master`` rows from CSV sources."""

    def load_active(self) -> List[LspMaster]:
        """Load active LSPs from the DB (compat shim for previous CSV loader)."""
        cf = ConnectionFactory()
        cf.create_all_tables(base=Base)
        session = cf.get_session()
        try:
            rows = session.query(LspMasterORM).filter_by(active=True).all()
            result: List[LspMaster] = []
            for r in rows:
                result.append(
                    LspMaster(
                        lsp_name=r.name,
                        disclosure_url=r.home_url or "",
                        is_active=bool(r.active),
                        fetch_hint="auto",
                        parse_hint="auto",
                        rules_json=None,
                        lsp_id=str(r.id),
                        home_url=r.home_url,
                        id=r.id,
                    )
                )
            return result
        finally:
            session.close()
