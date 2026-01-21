from __future__ import annotations

import os
import csv
import datetime as dt
from pathlib import Path
from typing import Iterable

from DatabaseOperation.SQLAlchemy.DatabaseModels import DlgRaw
from utils import parse_amount_any, parse_date_any, normalize_amount_to_crores
from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.SQLAlchemy.DatabaseModels.orm_models import DlgRawORM, Base, LspMasterORM
import re


class DlgRawManager:
    RAW_COLUMNS = [
        "LSP Name",
        "Lender",
        "Portfolio",
        "Amount",
        "AsOnTimestamp",
        "ScrapeTimestamp",
        "Complete",
    ]

    def append(self, rows: Iterable[DlgRaw]) -> None:
        # Persist rows to DB (CSV arguments removed; DB is source-of-truth)
        self._append_db(rows)

    def _append_db(self, rows: Iterable[DlgRaw]) -> None:
        conn_factory = ConnectionFactory()
        conn_factory.create_all_tables(base=Base)
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
                        lm = session.query(LspMasterORM).filter_by(name=identifier_str).one_or_none()
                        if lm:
                            lsp_id = lm.id
                if lsp_id is None:
                    # fallback - try to find by name
                    lm = session.query(LspMasterORM).filter_by(name=identifier_str).one_or_none()
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
                    exists = session.query(DlgRawORM).filter_by(
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

                db_row = DlgRawORM(
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
