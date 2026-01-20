from __future__ import annotations

from typing import Iterable, Optional
import datetime as dt

from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.SQLAlchemy.DatabaseModels.orm_models import DlgCrawlerConfigORM, Base
from DatabaseOperation.SQLAlchemy.DatabaseModels import DlgCrawlerConfig


class DlgCrawlerConfigManagerDB:
    """DB-backed manager for `dlg_crawler_config` rows."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.conn_factory = ConnectionFactory(db_path)
        self.conn_factory.create_all_tables(base=Base)

    def upsert(self, cfg: DlgCrawlerConfig, lsp_id: str, dlg_url: Optional[str] = None) -> None:
        session = self.conn_factory.get_session()
        try:
            existing = session.query(DlgCrawlerConfigORM).filter_by(lsp_id=lsp_id).one_or_none()
            if existing:
                # Use explicit dlg_url if provided; otherwise preserve existing value
                if dlg_url is not None:
                    existing.dlg_url = dlg_url
                existing.is_active = cfg is not None and (existing.is_active or bool(cfg.fetch_hint))
                existing.fetch_hint = cfg.fetch_hint
                existing.parse_hint = cfg.parse_hint
                existing.rules_json = cfg.rules_json
            else:
                row = DlgCrawlerConfigORM(
                    lsp_id=lsp_id,
                    dlg_url=dlg_url or "",
                    is_active=True,
                    fetch_hint=cfg.fetch_hint,
                    parse_hint=cfg.parse_hint,
                    rules_json=cfg.rules_json,
                )
                session.add(row)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def bulk_upsert(self, rows: Iterable[tuple[str, DlgCrawlerConfig, Optional[str]]]) -> int:
        count = 0
        for lsp_id, cfg, dlg_url in rows:
            self.upsert(cfg, lsp_id, dlg_url)
            count += 1
        return count
