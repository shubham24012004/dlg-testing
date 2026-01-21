"""
DlgCrawlerManager with DB support for audit logs and raw data.
"""
from __future__ import annotations
import datetime as dt
from typing import Any, Dict, List, Optional, Tuple
from DatabaseOperation.SQLAlchemy.DatabaseModels.orm_models import AuditAction, LspMasterORM, DlgRawORM, AuditLogORM, Base
from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.SQLAlchemy.DatabaseModels import LspMaster, DlgRaw, AuditLog
from General.Managers.AuditLogManagerDB import AuditLogManagerDB
from utils import parse_amount_any, parse_date_any, normalize_amount_to_crores
import re

class DlgCrawlerManagerDB:
    """Coordinates fetching, parsing, and persistence for DLG disclosures (DB version)."""
    def __init__(self, db_path: str = None) -> None:
        self.conn_factory = ConnectionFactory(db_path)
        self.conn_factory.create_all_tables(base=Base)
        self.audit_manager = AuditLogManagerDB(db_path)

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
                        payload=str({"status": "Error", "details": str(exc)[:200], "ts": scrape_started_at.isoformat()}),
                    )
                )
                print(f"[ERR] {source.lsp_name} -> Error ({str(exc)[:120]})")

    def _persist_rows(self, status: str, normalized_rows: List[Dict[str, Any]], source: LspMaster, scrape_started_at: dt.datetime) -> None:
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
                        lm = session.query(LspMasterORM).filter_by(name=identifier_str).one_or_none()
                        if lm:
                            resolved_lsp_id = lm.id
                if resolved_lsp_id is None:
                    lm = session.query(LspMasterORM).filter_by(name=identifier_str).one_or_none()
                    if lm:
                        resolved_lsp_id = lm.id

                # avoid duplicates: check existing by resolved_lsp_id + lsp_name + lender + portfolio + as_on_timestamp
                as_on_ts = row.get("as_on_timestamp") or scrape_started_at
                lender = row.get("lender") or ""
                portfolio = row.get("portfolio") or ""
                exists = None
                try:
                    exists = session.query(DlgRawORM).filter_by(
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

                db_row = DlgRawORM(
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
                    lm = session.query(LspMasterORM).filter_by(name=source.lsp_id).one_or_none()
                    if lm:
                        resolved_lsp_id = lm.id
            if resolved_lsp_id is None:
                lm = session.query(LspMasterORM).filter_by(name=source.lsp_name).one_or_none()
                if lm:
                    resolved_lsp_id = lm.id

            db_row = DlgRawORM(
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

    def scrape_one(self, source: LspMaster) -> Tuple[str, Optional[str], Optional[str], List[Dict[str, Any]]]:
        # Placeholder: implement actual scraping logic or call legacy manager
        return "Success", None, None, [{"lsp_name": source.lsp_name, "status": "Success"}]
