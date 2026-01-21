from __future__ import annotations

from typing import Iterable, Optional
import datetime as dt

from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.SQLAlchemy.DatabaseModels.orm_models import LspMasterORM, Base, DlgCrawlerConfigORM
from DatabaseOperation.SQLAlchemy.DatabaseModels import LspMaster
import json
import datetime as dt
from typing import List


class LspMasterManagerDB:
    """DB-backed manager for `lsp_master` rows."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.conn_factory = ConnectionFactory(db_path)
        self.conn_factory.create_all_tables(base=Base)

    def upsert(self, lm: LspMaster) -> None:
        session = self.conn_factory.get_session()
        try:
            # Prefer matching by numeric id if provided, otherwise by name
            existing = None
            if lm.lsp_id is not None:
                try:
                    numeric = int(lm.lsp_id)
                    existing = session.query(LspMasterORM).filter_by(id=numeric).one_or_none()
                except Exception:
                    existing = session.query(LspMasterORM).filter_by(name=lm.lsp_name).one_or_none()
            else:
                existing = session.query(LspMasterORM).filter_by(name=lm.lsp_name).one_or_none()

            if existing:
                existing.name = lm.lsp_name
                existing.home_url = lm.disclosure_url
                existing.active = lm.is_active
            else:
                row = LspMasterORM(name=lm.lsp_name, home_url=lm.disclosure_url, active=lm.is_active)
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

    def load_active(self) -> List[LspMaster]:
        """Load active LSPs from the DB (compat shim for CSV-based loader)."""
        session = self.conn_factory.get_session()
        try:
            rows = session.query(LspMasterORM).filter_by(active=True).all()
            result: List[LspMaster] = []
            for r in rows:
                # fetch crawler config (fetch_hint/parse_hint/rules_json)
                cfg = session.query(DlgCrawlerConfigORM).filter_by(lsp_id=r.id).one_or_none()
                rules = None
                fetch_hint = "auto"
                parse_hint = "auto"
                if cfg:
                    fetch_hint = (cfg.fetch_hint or "auto")
                    parse_hint = (cfg.parse_hint or "auto")
                if cfg and cfg.rules_json is not None:
                    try:
                        # cfg.rules_json may be stored as text; parse to mapping if needed
                        rules = cfg.rules_json if isinstance(cfg.rules_json, dict) else json.loads(cfg.rules_json)
                    except Exception:
                        # fallback to None on parse error
                        rules = None
                result.append(
                    LspMaster(
                        lsp_name=r.name,
                        disclosure_url=r.home_url or "",
                        is_active=bool(r.active),
                        fetch_hint=fetch_hint,
                        parse_hint=parse_hint,
                        rules_json=rules,
                        lsp_id=str(r.id),
                        home_url=r.home_url,
                        id=r.id,
                    )
                )
            return result
        finally:
            session.close()
