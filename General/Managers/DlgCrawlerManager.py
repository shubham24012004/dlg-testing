"""
DlgCrawlerService with DB support for audit logs and raw data.
"""
import datetime as dt
from typing import Any, Dict, List, Optional, Tuple, Iterable
from DatabaseOperation.DatabaseModels.orm_models import AuditAction
from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.DatabaseModels.orm_models import LspMaster, DlgRaw
from General.Managers.AuditLogManager import AuditLogManager
from utils.utils import parse_amount_any, parse_date_any, normalize_amount_to_crores
import re
from utils.logger_config import logger_method


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

    def run(self, sources: List[LspMaster], limit: Optional[int] = None) -> None:
        if limit:
            sources = sources[:limit]
        for source in sources:
            scrape_started_at = dt.datetime.utcnow()
            try:
                status, *_rest, normalized_rows = self.scrape_one(source)
                self._persist_rows(status, normalized_rows, source, scrape_started_at)
                self.audit_manager.record(
                    self.audit_manager.build(
                        lsp_id=(source.lsp_id or source.lsp_name),
                        action_taken=AuditAction.CRAWL,
                        auto_manual="auto",
                        user_id="system",
                        payload=str({"status": status, "ts": scrape_started_at.isoformat()}),
                    )
                )
                print(f"[OK] {source.lsp_name} -> {status}")
            except Exception as exc:
                self._persist_error(source, scrape_started_at)
                self.audit_manager.record(
                    self.audit_manager.build(
                        lsp_id=(source.lsp_id or source.lsp_name),
                        action_taken=AuditAction.CRAWL,
                        auto_manual="auto",
                        user_id="system",
                        payload=str(
                            {"status": "Error", "details": str(exc)[:200], "ts": scrape_started_at.isoformat()}),
                    )
                )
                print(f"[ERR] {source.lsp_name} -> Error ({str(exc)[:120]})")

    def _persist_rows(self, status: str, normalized_rows: List[Dict[str, Any]], source: LspMaster,
                      scrape_started_at: dt.datetime) -> None:
        session = self.conn_factory.get_session()
        try:
            for row in normalized_rows:
                # resolve numeric PK for lsp_id
                resolved_lsp_id = None
                identifier_str = row.get("lsp_id") or source.lsp_id or source.lsp_name
                if row.get("lsp_id") is not None:
                    try:
                        resolved_lsp_id = int(row.get("lsp_id"))
                    except Exception:
                        lm = session.query(LspMaster).filter_by(name=identifier_str).one_or_none()
                        if lm:
                            resolved_lsp_id = lm.id
                if resolved_lsp_id is None:
                    lm = session.query(LspMaster).filter_by(name=identifier_str).one_or_none()
                    if lm:
                        resolved_lsp_id = lm.id

                # avoid duplicates: check existing by resolved_lsp_id + lsp_name + lender + portfolio + as_on_timestamp
                as_on_ts = row.get("as_on_timestamp") or scrape_started_at
                lender = row.get("lender") or ""
                portfolio = row.get("portfolio") or ""
                exists = None
                try:
                    exists = session.query(DlgRaw).filter_by(
                        lsp_id=resolved_lsp_id,
                        lsp_name=row.get("lsp_name", source.lsp_name),
                        lender=lender,
                        portfolio=portfolio,
                        as_on_timestamp=as_on_ts,
                    ).one_or_none()
                except Exception:
                    exists = None

                if exists:
                    continue

                # Coerce amount
                amount_val = None
                raw_amount = row.get("amount")
                if raw_amount is not None:
                    if isinstance(raw_amount, (int, float)):
                        amount_val = float(raw_amount)
                    else:
                        parsed = parse_amount_any(raw_amount)
                        if parsed is not None:
                            amount_val = normalize_amount_to_crores(parsed)

                # Heuristics: recover amount from portfolio/lender if needed
                if amount_val is None and isinstance(portfolio, str) and re.search(r"\d", portfolio):
                    parsed = parse_amount_any(portfolio)
                    if parsed is not None:
                        amount_val = normalize_amount_to_crores(parsed)
                        portfolio = ""
                if amount_val is None and isinstance(lender, str) and re.search(r"\d", lender):
                    parsed = parse_amount_any(lender)
                    if parsed is not None:
                        amount_val = normalize_amount_to_crores(parsed)
                        lender = ""

                # Coerce date
                if isinstance(as_on_ts, dt.datetime):
                    as_on_ts_parsed = as_on_ts
                else:
                    as_on_ts_parsed = parse_date_any(as_on_ts)

                db_row = DlgRaw(
                    lsp_id=resolved_lsp_id,
                    lsp_name=row.get("lsp_name", source.lsp_name),
                    lender=lender,
                    portfolio=portfolio,
                    amount=amount_val,
                    as_on_timestamp=as_on_ts_parsed,
                    scrape_timestamp=scrape_started_at,
                    complete=status,
                )
                session.merge(db_row)
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"[DlgCrawlerManagerDB] Error persisting rows: {e}")
        finally:
            session.close()

    def _persist_error(self, source: LspMaster, scrape_started_at: dt.datetime) -> None:
        session = self.conn_factory.get_session()
        try:
            # resolve numeric PK for source
            resolved_lsp_id = None
            if source.lsp_id is not None:
                try:
                    resolved_lsp_id = int(source.lsp_id)
                except Exception:
                    lm = session.query(LspMaster).filter_by(name=source.lsp_id).one_or_none()
                    if lm:
                        resolved_lsp_id = lm.id
            if resolved_lsp_id is None:
                lm = session.query(LspMaster).filter_by(name=source.lsp_name).one_or_none()
                if lm:
                    resolved_lsp_id = lm.id

            db_row = DlgRaw(
                lsp_id=resolved_lsp_id,
                lsp_name=source.lsp_name,
                lender="",
                portfolio="",
                amount=None,
                as_on_timestamp=scrape_started_at,
                scrape_timestamp=scrape_started_at,
                complete="Error",
            )
            session.add(db_row)
            session.commit()
        except Exception as e:
            session.rollback()
            print(f"[DlgCrawlerManagerDB] Error persisting error row: {e}")
        finally:
            session.close()

    @staticmethod
    def scrape_one(source: LspMaster) -> Tuple[str, Optional[str], Optional[str], List[Dict[str, Any]]]:
        # Placeholder: implement actual scraping logic or call legacy manager
        return "Success", None, None, [{"lsp_name": source.lsp_name, "status": "Success"}]

    @staticmethod
    def append(rows: Iterable[DlgRaw]) -> None:
        conn_factory = ConnectionFactory()
        session = conn_factory.get_session()
        try:
            for row in rows:
                # resolve numeric PK for lsp_id when possible
                lsp_id = None
                identifier_str = row.lsp_id or row.lsp_name
                if row.lsp_id is not None:
                    try:
                        lsp_id = int(row.lsp_id)
                    except Exception:
                        lm = session.query(LspMaster).filter_by(name=identifier_str).one_or_none()
                        if lm:
                            lsp_id = lm.id
                if lsp_id is None:
                    # fallback - try to find by name
                    lm = session.query(LspMaster).filter_by(name=identifier_str).one_or_none()
                    if lm:
                        lsp_id = lm.id
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

    @staticmethod
    def _format_dt(value: dt.datetime | str | None, *, with_time: bool = False) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return value.strftime("%Y-%m-%d %H:%M:%S" if with_time else "%Y-%m-%d")
