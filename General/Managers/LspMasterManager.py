from typing import Optional, Any

from sqlalchemy import asc

from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.DatabaseModels.orm_models import LspMaster, Base, DlgRaw
from utils.logger_config import logger_method


class LspMasterManager:
    """DB-backed manager for `lsp_master` rows."""

    def __init__(self, db_path: Optional[str] = None):
        self.conn_factory = ConnectionFactory()
        self.conn_factory.create_all_tables(base=Base)
        self.logger = logger_method(__name__)

    def insert(self, lm: LspMaster) -> Any:
        session = self.conn_factory.get_session()
        try:
            existing = session.query(LspMaster).filter_by(home_url=lm.home_url).one_or_none()

            if existing:
                self.logger.error('LSP already exists')
                return None
            else:
                existing = session.query(LspMaster).filter_by(name=lm.name).one_or_none()
                if existing:
                    self.logger.error('LSP already exists')
                    return None

                row = LspMaster(name=lm.name, home_url=lm.home_url, active=True, dlg_url=lm.dlg_url,
                                parse_hint=lm.parse_hint, fetch_hint=lm.fetch_hint, rules_json=lm.rules_json)
                session.add(row)
            session.commit()
            self.logger.info(f'{lm.name} LSP Added Successfully')
            result_dict = {"id": row.id, "name": row.name, "active": row.active, "home_url": row.home_url,
                           "dlg_url": row.dlg_url, "parse_hint": row.parse_hint, "fetch_hint": row.fetch_hint,
                           "rules_json": row.rules_json, "last_crawl_date": row.last_crawl_date}
            return result_dict
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update(self, lm: LspMaster) -> Any:
        session = self.conn_factory.get_session()
        try:
            existing_lsp = session.query(LspMaster).filter_by(id=lm.id).one_or_none()

            if not existing_lsp:
                self.logger.error('LSP not found')
                return None
            else:
                scraped = session.query(DlgRaw).filter_by(lsp_id=lm.id).one_or_none()
                if not scraped:
                    # can update all Data as LSP has NOT been scraped and there is NO raw data.
                    existing_lsp.name = lm.name
                    existing_lsp.home_url = lm.home_url

                # can update DLG URL only as LSP has been scraped and there is raw data. cannot break integrity
                existing_lsp.dlg_url = lm.dlg_url
                # existing_lsp.rules_json = lm.rules_json
                # existing_lsp.fetch_hint = lm.fetch_hint
                # existing_lsp.parse_hint = lm.parse_hint

                session.add(existing_lsp)
            session.commit()
            self.logger.info(f'{lm.name} LSP Updated Successfully')
            result_dict = {"id": existing_lsp.id, "name": existing_lsp.name, "active": existing_lsp.active,
                           "home_url": existing_lsp.home_url,
                           "dlg_url": existing_lsp.dlg_url, "parse_hint": existing_lsp.parse_hint,
                           "fetch_hint": existing_lsp.fetch_hint,
                           "rules_json": existing_lsp.rules_json, "last_crawl_date": existing_lsp.last_crawl_date}
            return result_dict
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def delete(self, lsp_id: int) -> int:
        session = self.conn_factory.get_session()
        try:
            existing = session.query(LspMaster).filter_by(active=True).filter_by(id=lsp_id).one_or_none()

            if existing:
                existing.active = False
                session.add(existing)
            else:
                self.logger.error('LSP Not found')
                return 0
            session.commit()
            self.logger.error(f'{existing.name} LSP Deleted Successfully')
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        return lsp_id

    def list_lsp_master(
            self, active_only: bool = False, per_page: int = None, page: int = None, lsp_id: int = None,
            lsp_name: str = None
    ) -> tuple[list[dict[Any, Any] | dict[str, Any] | dict[str, str]], Any]:
        """List LSP master records.

        Args:
            :param lsp_id: lsp id to search by
            :param lsp_name: search string for name of lsp
            :param active_only: If True, only return active LSPs
            :param page: page number
            :param per_page: page size

        Returns:
            List of dict of filtered LspMaster
            count
        """

        session = self.conn_factory.get_session()
        try:
            query = session.query(LspMaster).order_by(asc(LspMaster.name))
            if active_only:
                query = query.filter_by(active=True)
            if lsp_id:
                query = query.filter_by(id=lsp_id)
            if lsp_name:
                search_name = f'%{lsp_name}%'
                query = query.filter(LspMaster.name.like(search_name))
            if page:
                query = query.offset((page - 1) * per_page)
            if per_page:
                query = query.limit(per_page)
            rows = query.all()
            result = []
            for row in rows:
                result_dict = {"id": row.id, "name": row.name, "active": row.active, "home_url": row.home_url,
                               "dlg_url": row.dlg_url, "parse_hint": row.parse_hint, "fetch_hint": row.fetch_hint,
                               "rules_json": row.rules_json, "last_crawl_date": row.last_crawl_date}
                result.append(result_dict)
            return result, len(result)
        except Exception as ex:
            self.logger.error(f'Exception in list_lsp_master {ex}')
            raise
        finally:
            session.close()
