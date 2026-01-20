from __future__ import annotations

import os
import csv
import datetime as dt
from pathlib import Path
from typing import Iterable

from DatabaseOperation.SQLAlchemy.DatabaseModels import DlgRaw
from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.SQLAlchemy.DatabaseModels.orm_models import DlgRawORM, Base, LspMasterORM


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

    def append(self, raw_csv_path: str | Path, rows: Iterable[DlgRaw]) -> None:
        raw_csv_path = Path(raw_csv_path)
        file_exists = raw_csv_path.exists()
        with raw_csv_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=self.RAW_COLUMNS)
            if not file_exists:
                writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "LSP Name": row.lsp_name,
                        "Lender": row.lender,
                        "Portfolio": row.portfolio,
                        "Amount": row.amount,
                        "AsOnTimestamp": self._format_dt(row.as_on_timestamp),
                        "ScrapeTimestamp": self._format_dt(row.scrape_timestamp, with_time=True),
                        "Complete": row.complete,
                    }
                )

        self._append_db(rows)

    def _append_db(self, rows: Iterable[DlgRaw]) -> None:
        conn_factory = ConnectionFactory()
        conn_factory.create_all_tables(base=Base)
        session = conn_factory.get_session()
        try:
            for row in rows:
                # resolve numeric PK for lsp_id when possible
                lsp_id = None
                legacy = row.lsp_id or row.lsp_name
                if row.lsp_id is not None:
                    try:
                        lsp_id = int(row.lsp_id)
                    except Exception:
                        lm = session.query(LspMasterORM).filter_by(legacy_id=legacy).one_or_none()
                        if lm:
                            lsp_id = lm.id
                if lsp_id is None:
                    # fallback - try to find by legacy name
                    lm = session.query(LspMasterORM).filter_by(legacy_id=legacy).one_or_none()
                    if lm:
                        lsp_id = lm.id
                lender = row.lender or ""
                portfolio = row.portfolio or ""
                as_on_ts = row.as_on_timestamp or row.scrape_timestamp
                scrape_ts = row.scrape_timestamp or dt.datetime.utcnow()
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
                    amount=row.amount,
                    as_on_timestamp=as_on_ts,
                    scrape_timestamp=scrape_ts,
                    complete=row.complete,
                )
                session.add(db_row)
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
