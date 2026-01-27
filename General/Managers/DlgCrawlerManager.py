"""
DlgCrawlerService with DB support for audit logs and raw data.
"""
import re
import datetime as dt
from typing import Iterable
from utils.logger_config import logger_method
from General.Managers.AuditLogManager import AuditLogManager
from DatabaseOperation.DatabaseModels.orm_models import LspMaster, DlgRaw
from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from utils.utils import parse_amount_any, parse_date_any, normalize_amount_to_crores


class DlgCrawlerManager:
    """Coordinates fetching, parsing, and persistence for DLG disclosures (DB version)."""

    RAW_COLUMNS = [
        "LSP Name",
        "Lender",
        "Portfolio",
        "Amount",
        "AsOnTimestamp",
        "ScrapeTimestamp",
        "Complete",
    ]

    def __init__(self):
        self.logger = logger_method(__name__)
        self.conn_factory = ConnectionFactory()
        self.audit_manager = AuditLogManager()

    @staticmethod
    def append(rows: Iterable[DlgRaw]) -> None:
        conn_factory = ConnectionFactory()
        session = conn_factory.get_session()
        try:
            for row in rows:
                lsp_id = row.lsp_id
                lsp_name = row.lsp_name
                lender = row.lender or ""
                portfolio = row.portfolio or ""
                as_on_ts = row.as_on_timestamp or row.scrape_timestamp
                scrape_ts = row.scrape_timestamp or dt.datetime.utcnow()

                # Coerce/validate amount: parse strings like '1,234,567' into floats (crores)
                amount_val = None
                if row.amount is not None:
                    if isinstance(row.amount, (int, float)):
                        amount_val = float(row.amount)
                    else:
                        parsed = parse_amount_any(row.amount)
                        if parsed is not None:
                            amount_val = normalize_amount_to_crores(parsed)

                # Heuristic: if amount missing but portfolio looks numeric, treat portfolio as amount
                if amount_val is None and isinstance(portfolio, str) and re.search(r"\d", portfolio):
                    parsed = parse_amount_any(portfolio)
                    if parsed is not None:
                        amount_val = normalize_amount_to_crores(parsed)
                        portfolio = ""

                # If lender looks numeric and amount missing, try to recover
                if amount_val is None and isinstance(lender, str) and re.search(r"\d", lender):
                    parsed = parse_amount_any(lender)
                    if parsed is not None:
                        amount_val = normalize_amount_to_crores(parsed)
                        lender = ""

                # Coerce/validate as_on_timestamp
                if isinstance(as_on_ts, dt.datetime):
                    as_on_ts_parsed = as_on_ts
                else:
                    as_on_ts_parsed = parse_date_any(as_on_ts)
                # avoid inserting duplicates: match on lsp_id + lsp_name + lender + portfolio + as_on_timestamp
                exists = None
                try:
                    exists = session.query(DlgRaw).filter_by(
                        lsp_id=lsp_id,
                        lsp_name=row.lsp_name,
                        lender=lender,
                        portfolio=portfolio,
                        as_on_timestamp=as_on_ts,
                    ).one_or_none()
                except Exception:
                    exists = None

                if exists:
                    # skip duplicate
                    continue

                db_row = DlgRaw(
                    lsp_id=lsp_id,
                    lsp_name=row.lsp_name,
                    lender=lender,
                    portfolio=portfolio,
                    amount=amount_val,
                    as_on_timestamp=as_on_ts_parsed,
                    scrape_timestamp=scrape_ts,
                    complete=row.complete,
                )
                # use merge to avoid identity-map collisions when detached/duplicate PKs are present
                session.merge(db_row)
            session.commit()
        except Exception as exc:
            session.rollback()
            print(f"[DlgRawManager] DB append failed: {exc}")
        finally:
            session.close()
