"""
DlgCrawlerService with DB support for audit logs and raw data.
"""
import re
import datetime as dt
from sqlalchemy import extract  
from typing import Iterable, Optional, Dict, Any
from utils.constants import CrawlStatus
from utils.logger_config import logger_method
from Managers.AuditLogManager import AuditLogManager
from DatabaseOperation.DatabaseModels.master_models import DlgRaw
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

    def __init__(self, user_claims: Optional[Dict[str, Any]] = None):
        self.logger = logger_method(__name__)
        self.user_claims = user_claims
        self.conn_factory = ConnectionFactory()
        self.audit_manager = AuditLogManager(user_claims=user_claims)

    def _get_user_info(self) -> str:
        """Get formatted user info string from user_claims."""
        if not self.user_claims:
            return "[User: system, Role: unknown]"
        username = self.user_claims.get('username', 'unknown')
        user_role = self.user_claims.get('role', 'unknown')
        return f"[User: {username}, Role: {user_role}]"

    def get_existing_rows(self, source_id: int, as_on_timestamp: dt.datetime, scrape_timestamp: dt.datetime) -> Iterable[DlgRaw]:
        """Check for existing rows with same lsp_id + as_on_timestamp and stale status."""
        session = self.conn_factory.get_session()
        try:
            existing = []            
            existing = session.query(DlgRaw).filter_by(
                lsp_id=source_id,
                # as_on_timestamp=as_on_timestamp,
                complete=CrawlStatus.STALE.value
            ).filter( # compare only scrape month and year skip day also for duplicate check to handle cases where as_on_timestamp is same across months but different scrapes
                extract('year', DlgRaw.scrape_timestamp) == scrape_timestamp.year,
                extract('month', DlgRaw.scrape_timestamp) == scrape_timestamp.month
            ).all()            
            return existing
        except Exception as exc:
            self.logger.error(f"{self._get_user_info()} Error checking existing DlgRaw rows: {exc}")
            return []
        finally:
            session.close()
            
    def append(self, rows: Iterable[DlgRaw]) -> None:
        conn_factory = ConnectionFactory()
        session = conn_factory.get_session()
        try:
            for row in rows:
                # Create payload dict from row object
                payload = {
                    "lsp_id": row.lsp_id,
                    "lsp_name": row.lsp_name,
                    "lender": row.lender,
                    "portfolio": row.portfolio,
                    "amount": row.amount,
                    "as_on_timestamp": row.as_on_timestamp,
                    "scrape_timestamp": row.scrape_timestamp,
                    "complete": row.complete,
                    "dlg_url": row.dlg_url
                }
                
                lsp_id = row.lsp_id
                lender = row.lender or ""
                portfolio = row.portfolio or ""
                as_on_ts = row.as_on_timestamp
                scrape_ts = row.scrape_timestamp or dt.datetime.now(tz=dt.timezone.utc)

                # Coerce/validate amount: parse strings like '1,234,567' into floats (crores)
                amount_val = None
                if row.amount is not None:
                    if isinstance(row.amount, (int, float)):
                        amount_val = float(row.amount)
                    else:

                        parsed = parse_amount_any(row.amount)
                        if parsed is not None:
                            amount_val = normalize_amount_to_crores(parsed)

                # Heuristic: if amount missing but portfolio looks like a bare number/amount,
                # treat portfolio as amount. Only applies when portfolio starts with a digit
                # or currency symbol — NOT for labelled values like "Portfolio 1".
                if amount_val is None and isinstance(portfolio, str) and re.match(r'^\s*[\d₹]', portfolio):
                    parsed = parse_amount_any(portfolio)
                    if parsed is not None:
                        amount_val = normalize_amount_to_crores(parsed)
                        portfolio = ""

                # If lender looks like a proper amount (not a simple 1-3 digit index) and
                # amount is missing, try to recover.
                if amount_val is None and isinstance(lender, str) and re.search(r"\d", lender):
                    stripped_lender = lender.strip()
                    # Skip simple integer indices like "1", "2", "12" — these are lender IDs
                    if not re.fullmatch(r'\d{1,3}', stripped_lender):
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
                exists = session.query(DlgRaw).filter_by(
                    lsp_id=lsp_id,
                    lsp_name=row.lsp_name,
                    lender=lender,
                    portfolio=portfolio,
                    as_on_timestamp=as_on_ts
                ).filter( # compare only scrape month and year skip day also for duplicate check to handle cases where as_on_timestamp is same across months but different scrapes
                    extract('year', DlgRaw.scrape_timestamp) == scrape_ts.year,
                    extract('month', DlgRaw.scrape_timestamp) == scrape_ts.month
                ).first()

                if exists:
                    # skip duplicate
                    self.logger.info(f"{self._get_user_info()} DLG row processed - status=skipped_duplicate, payload={payload}")
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
                    dlg_url=row.dlg_url
                )
                # use merge to avoid identity-map collisions when detached/duplicate PKs are present
                session.merge(db_row)
                
                # Log successful row processing
                self.logger.info(f"{self._get_user_info()} DLG row processed - status=inserted, payload={payload}")
            session.commit()
        except Exception as exc:
            session.rollback()
            self.logger.error(f"{self._get_user_info()} [DlgRawManager] DB append failed: {exc}")
        finally:
            session.close()
