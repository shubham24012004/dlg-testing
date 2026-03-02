"""
DlgRawManager for add, update, and delete of DlgRaw records.
"""
import datetime as dt
from typing import Optional, Dict, Any

from sqlalchemy.exc import SQLAlchemyError

from DatabaseOperation.DatabaseModels.master_models import DlgRaw, Base, DlgRawInput, DlgRawUpdate
from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from utils.logger_config import logger_method


class DlgRawManager:
    """DB-backed manager for `dlg_raw` rows."""

    def __init__(self, user_claims: Optional[Dict[str, Any]] = None):
        self.conn_factory = ConnectionFactory()
        self.conn_factory.create_all_tables(base=Base)
        self.user_claims = user_claims
        self.logger = logger_method(__name__)

    def _get_user_info(self) -> str:
        """Get formatted user info string from user_claims."""
        if not self.user_claims:
            return "[User: system, Role: unknown]"
        username = self.user_claims.get('username', 'unknown')
        user_role = self.user_claims.get('role', 'unknown')
        return f"[User: {username}, Role: {user_role}]"

    def insert(self, raw_input: DlgRawInput) -> Optional[Dict[str, Any]]:
        """Insert a new DlgRaw record.

        Args:
            raw_input: DlgRawInput dataclass with required fields lsp_id and lsp_name.

        Returns:
            dict with the created record summary, or None if a duplicate exists.
        """
        session = self.conn_factory.get_session()
        try:
            existing = session.query(DlgRaw).filter_by(
                lsp_id=raw_input.lsp_id,
                lsp_name=raw_input.lsp_name,
                lender=raw_input.lender,
                portfolio=raw_input.portfolio,
                as_on_timestamp=raw_input.as_on_timestamp,
            ).one_or_none()

            if existing:
                self.logger.error(f"{self._get_user_info()} DlgRaw record already exists")
                return None

            now = dt.datetime.now(tz=dt.timezone.utc)
            row = DlgRaw(
                lsp_id=raw_input.lsp_id,
                lsp_name=raw_input.lsp_name,
                lender=raw_input.lender,
                portfolio=raw_input.portfolio,
                amount=raw_input.amount,
                as_on_timestamp=raw_input.as_on_timestamp,
                scrape_timestamp=raw_input.scrape_timestamp or now,
                complete=raw_input.complete,
                dlg_url=raw_input.dlg_url,
            )
            session.add(row)
            session.commit()
            self.logger.info(
                f"{self._get_user_info()} DlgRaw record added for LSP {raw_input.lsp_name} (id={raw_input.lsp_id})"
            )
            return {
                "id": row.id,
                "lsp_id": row.lsp_id,
                "lsp_name": row.lsp_name,
                "lender": row.lender,
                "portfolio": row.portfolio,
                "amount": row.amount,
                "as_on_timestamp": str(row.as_on_timestamp),
                "scrape_timestamp": str(row.scrape_timestamp),
                "complete": row.complete,
                "dlg_url": row.dlg_url,
            }
        except SQLAlchemyError:
            session.rollback()
            raise
        finally:
            session.close()

    def update(self, raw_update: DlgRawUpdate) -> Optional[Dict[str, Any]]:
        """Update an existing DlgRaw record by its primary id.

        Args:
            raw_update: DlgRawUpdate dataclass; only non-None fields are applied.

        Returns:
            dict with the updated record summary, or None if the record is not found.
        """
        session = self.conn_factory.get_session()
        try:
            existing = session.query(DlgRaw).filter_by(id=raw_update.id).one_or_none()

            if not existing:
                self.logger.error(f"{self._get_user_info()} DlgRaw record with id={raw_update.id} not found")
                return None

            if raw_update.lsp_id is not None:
                existing.lsp_id = raw_update.lsp_id
            if raw_update.lsp_name is not None:
                existing.lsp_name = raw_update.lsp_name
            if raw_update.lender is not None:
                existing.lender = raw_update.lender
            if raw_update.portfolio is not None:
                existing.portfolio = raw_update.portfolio
            if raw_update.amount is not None:
                existing.amount = raw_update.amount
            if raw_update.as_on_timestamp is not None:
                existing.as_on_timestamp = raw_update.as_on_timestamp
            if raw_update.scrape_timestamp is not None:
                existing.scrape_timestamp = raw_update.scrape_timestamp
            if raw_update.complete is not None:
                existing.complete = raw_update.complete
            if raw_update.dlg_url is not None:
                existing.dlg_url = raw_update.dlg_url

            session.add(existing)
            session.commit()
            self.logger.info(
                f"{self._get_user_info()} DlgRaw record id={raw_update.id} (lsp_id={existing.lsp_id}) updated successfully"
            )
            return {
                "id": existing.id,
                "lsp_id": existing.lsp_id,
                "lsp_name": existing.lsp_name,
                "lender": existing.lender,
                "portfolio": existing.portfolio,
                "amount": existing.amount,
                "as_on_timestamp": str(existing.as_on_timestamp),
                "scrape_timestamp": str(existing.scrape_timestamp),
                "complete": existing.complete,
                "dlg_url": existing.dlg_url,
            }
        except SQLAlchemyError:
            session.rollback()
            raise
        finally:
            session.close()

    def delete(self, raw_id: int) -> int:
        """Delete a DlgRaw record by its primary id.

        Args:
            raw_id: The integer primary key of the DlgRaw row to delete.

        Returns:
            raw_id if deleted, 0 if not found.
        """
        session = self.conn_factory.get_session()
        try:
            existing = session.query(DlgRaw).filter_by(id=raw_id).one_or_none()

            if not existing:
                self.logger.error(f"{self._get_user_info()} DlgRaw record with id={raw_id} not found")
                return 0

            lsp_id = existing.lsp_id
            session.delete(existing)
            session.commit()
            self.logger.info(f"{self._get_user_info()} DlgRaw record id={raw_id} (lsp_id={lsp_id}) deleted successfully")
            return {"id": raw_id, "lsp_id": lsp_id}
        except SQLAlchemyError:
            session.rollback()
            raise
        finally:
            session.close()
