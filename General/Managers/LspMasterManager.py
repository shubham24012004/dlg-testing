from typing import Optional

from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.DatabaseModels.orm_models import LspMaster, Base, LspMasterIp
from utils.logger_config import logger_method
from typing import List


class LspMasterManager:
    """DB-backed manager for `lsp_master` rows."""

    def __init__(self, db_path: Optional[str] = None):
        self.conn_factory = ConnectionFactory(db_path)
        self.conn_factory.create_all_tables(base=Base)
        self.logger = logger_method(__name__)

    def insert(self, lm: LspMasterIp) -> bool:
        session = self.conn_factory.get_session()
        try:
            existing = session.query(LspMaster).filter_by(name=lm.lsp_name).one_or_none()

            if existing:
                self.logger.error('LSP already exists')
                return False
            else:
                row = LspMaster(name=lm.lsp_name, home_url=lm.lsp_home_url, active=True)
                session.add(row)
            session.commit()
            self.logger.info('{0} LSP Added Successfully', lm.lsp_name)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        return True

    def update(self, lm: LspMaster) -> LspMaster | None:
        session = self.conn_factory.get_session()
        try:
            existing_lsp = session.query(LspMaster).filter_by(name=lm.id).one_or_none()

            if not existing_lsp:
                self.logger.error('LSP not found')
                return None
            else:
                existing_lsp.name = lm.name
                existing_lsp.home_url = lm.home_url
                existing_lsp.dlg_url = lm.dlg_url
                # existing_lsp.rules_json = lm.rules_json
                # existing_lsp.fetch_hint = lm.fetch_hint
                # existing_lsp.parse_hint = lm.parse_hint
                session.add(existing_lsp)
            session.commit()
            self.logger.info('{0} LSP Updated Successfully', lm.lsp_name)
            return existing_lsp
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete(self, lsp_id: int) -> bool:
        session = self.conn_factory.get_session()
        try:
            existing = session.query(LspMaster).filter_by(id=lsp_id).one_or_none()

            if existing:
                existing.active = False
                session.add(existing)
            else:
                self.logger.error('LSP Not found')
            session.commit()
            self.logger.error('{0} LSP Deleted Successfully', existing.lsp_name)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        return True

    def load_active(self) -> List[LspMaster]:
        """Load active LSPs from the DB """
        session = self.conn_factory.get_session()
        try:
            rows = session.query(LspMaster).filter_by(active=True).all()
            return rows
        finally:
            session.close()

    def get_lsp_master(self, id: int) -> Optional[LspMaster]:
        """Get LSP master by ID.

        Args:
            id: LSP ID

        Returns:
            LspMaster instance or None if not found
        """
        session = self.conn_factory.get_session()
        try:
            return session.query(LspMaster).filter_by(id=id).one_or_none()
        finally:
            session.close()

    def get_lsp_master_by_name(self, name: str) -> Optional[LspMaster]:
        """Get LSP master by name.

        Args:
            name: LSP name

        Returns:
            LspMaster instance or None if not found
        """
        session = self.conn_factory.get_session()
        try:
            return session.query(LspMaster).filter_by(name=name).one_or_none()
        finally:
            session.close()

    def list_lsp_master(
            self, active_only: bool = False, limit: int = None
    ) -> List[LspMaster]:
        """List LSP master records.

        Args:
            active_only: If True, only return active LSPs
            limit: Maximum number of records to return

        Returns:
            List of LspMaster instances
        """

        session = self.conn_factory.get_session()
        try:
            query = session.query(LspMaster)
            if active_only:
                query = query.filter_by(active=True)
            if limit:
                query = query.limit(limit)
            return query.all()
        finally:
            session.close()
