from typing import Optional, Dict
import datetime as dt
import pandas as pd

from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.DatabaseModels.report_models import Base, LspSummary
from DatabaseOperation.DatabaseModels.master_models import DlgRaw, CrawlStatus, LspMaster, AuditLog
from utils.logger_config import logger_method
from sqlalchemy import String, and_, or_, func, extract


class ReportsManager:
    """Manager to build and persist monthly LSP summaries into reports.lsp_summary."""

    def __init__(self, user_claims: Optional[Dict[str, str]] = None):
        self.conn_factory = ConnectionFactory()
        self.user_claims = user_claims
        # ensure report tables exist
        self.conn_factory.create_all_tables(base=Base)
        self.logger = logger_method(__name__)

    def _get_user_info(self) -> str:
        if not self.user_claims:
            return "[User: system, Role: unknown]"
        username = self.user_claims.get("username", "unknown")
        user_role = self.user_claims.get("role", "unknown")
        return f"[User: {username}, Role: {user_role}]"

    def lsp_summarize(self, start_date, end_date) -> int:
        """Summarize raw DLG data between start_date and end_date (inclusive) and upsert into lsp_summary.

        Args:
            start_date: date-like (str or datetime.date/datetime)
            end_date: date-like

        Returns:
            Number of summary rows upserted.
        """
        user_info = self._get_user_info()

        # Query DlgRaw rows from DB in the date range. scrape_timestamp between start_date and end_date
        session = self.conn_factory.get_session()
        try:
            rows = session.query(DlgRaw).filter(DlgRaw.scrape_timestamp.between(start_date, end_date)).all()
        except Exception as e:
            session.close()
            self.logger.error(f"{user_info} Failed to query DlgRaw rows: {e}")
            raise

        if not rows:
            session.close()
            self.logger.info(f"{user_info} No raw rows in date range {start_date} - {end_date}")
            return 0

        # Build DataFrame from rows
        records = []
        for r in rows:
            records.append({
                "lsp_id": r.lsp_id,
                "lsp_name": r.lsp_name,
                "portfolio": r.portfolio,
                "lender": r.lender,
                "amount": r.amount,
                "status": r.complete,
                "dlg_url": r.dlg_url,
                "as_on_timestamp": r.as_on_timestamp,
                "scrape_timestamp": r.scrape_timestamp,
            })

        df = pd.DataFrame.from_records(records)

        # ensure timestamps are datetime
        if "as_on_timestamp" in df.columns:
            df["as_on_timestamp"] = pd.to_datetime(df["as_on_timestamp"], errors="coerce")
        df["scrape_timestamp"] = pd.to_datetime(df["scrape_timestamp"], errors="coerce")

        # Add a column to determine the month window each record belongs to
        # Records between 8th of month X to 8th of month X+1 belong to month X
        def get_month_window(ts):
            """Return (year, month) for the month window this timestamp belongs to."""
            if pd.isna(ts):
                return None
            day = ts.day
            month = ts.month
            year = ts.year
            # If day >= 8, this record belongs to the current month window
            # If day < 8, it belongs to the previous month window
            if day < 8:
                if month == 1:
                    return year - 1, 12
                else:
                    return year, month - 1
            else:
                return year, month

        df["month_window"] = df["scrape_timestamp"].apply(get_month_window)

        # group by lsp_id, lsp_name, and month_window
        grouped = df.groupby(["lsp_id", "lsp_name", "month_window"])

        summaries = []
        for (lsp_id, name, month_window), grp in grouped:
            status: CrawlStatus = CrawlStatus.MISSING
            total_amount = 0.0
            total_portfolios = 0

            if grp['status'].notna().any():
                status = CrawlStatus(grp['status'].iloc[0])

            dlg_url = None
            if grp['dlg_url'].notna().any():
                dlg_url = grp['dlg_url'].iloc[0]

            total_amount = float(grp["amount"].fillna(0.0).sum())
            if "portfolio" in grp.columns:
                total_portfolios = int(grp.loc[grp["portfolio"].notna() & (grp["portfolio"] != ""), "portfolio"].nunique())
            else:
                total_portfolios = int(grp.shape[0])

            if "lender" in grp.columns:
                total_lenders = int(grp.loc[grp["lender"].notna() & (grp["lender"] != ""), "lender"].nunique())
            else:
                total_lenders = int(grp.shape[0])

            if total_portfolios < total_lenders:
                total_portfolios = total_lenders
            last_scrape = None
            if grp["scrape_timestamp"].notna().any():
                last_scrape = grp["scrape_timestamp"].max()

            last_ason = None
            if grp["as_on_timestamp"].notna().any():
                last_ason = grp["as_on_timestamp"].max()

            # Extract scrape_year and scrape_month from the month_window
            scrape_year = month_window[0]
            scrape_month = month_window[1]

            if last_ason:
                as_on_year = int(last_ason.year)
                as_on_month = int(last_ason.month)
            else:
                as_on_year = 0
                as_on_month = 0

            # Validate: as_on_timestamp should be from the previous month of scrape_timestamp
            # If not, mark status as "Stale"
            if last_ason and last_scrape:
                # Calculate previous month
                if scrape_month == 1:
                    prev_year = scrape_year - 1
                    prev_month = 12
                else:
                    prev_year = scrape_year
                    prev_month = scrape_month - 1

                # Check if as_on_timestamp is from the previous month
                if as_on_year != prev_year or as_on_month != prev_month:
                    status = CrawlStatus.STALE

            summaries.append({
                "lsp_id": int(lsp_id),
                "name": str(name),
                "total_portfolios": total_portfolios,
                "total_lenders": total_lenders,
                "total_amount": total_amount,
                "as_on_year": as_on_year,
                "as_on_month": as_on_month,
                "scrape_year": scrape_year,
                "scrape_month": scrape_month,
                "status": status,
                "dlg_url": dlg_url,
                "last_crawl_date": pd.to_datetime(last_scrape).to_pydatetime() if pd.notnull(last_scrape) else None,
            })

        session.close()

        # upsert into DB
        session = self.conn_factory.get_session()
        upserted = 0
        try:
            for s in summaries:
                duplicates = session.query(LspSummary).filter_by(lsp_id=s["lsp_id"], scrape_year=s["scrape_year"],
                                                                  scrape_month=s["scrape_month"]).all()
                # Delete extra duplicates, keep only the first
                if len(duplicates) > 1:
                    for dup in duplicates[1:]:
                        session.delete(dup)
                    session.flush()
                existing = duplicates[0] if duplicates else None
                if existing:
                    existing.name = s["name"]
                    existing.total_portfolios = s["total_portfolios"]
                    existing.total_amount = s["total_amount"]
                    existing.as_on_year = s["as_on_year"]
                    existing.as_on_month = s["as_on_month"]
                    existing.scrape_year = s["scrape_year"]
                    existing.scrape_month = s["scrape_month"]
                    if isinstance(s["status"], CrawlStatus):
                        existing.status = s["status"].value
                    else:
                        existing.status = s["status"]
                    existing.dlg_url = s["dlg_url"]
                    existing.total_lenders = s["total_lenders"]
                    existing.last_crawl_date = s["last_crawl_date"]
                    session.add(existing)
                else:
                    rec = LspSummary(
                        lsp_id=s["lsp_id"],
                        name=s["name"],
                        total_portfolios=s["total_portfolios"],
                        total_amount=s["total_amount"],
                        as_on_year=s["as_on_year"],
                        as_on_month=s["as_on_month"],
                        scrape_year=s["scrape_year"],
                        scrape_month=s["scrape_month"],
                        status=s["status"].value,
                        total_lenders=s["total_lenders"],
                        dlg_url=s["dlg_url"],
                        last_crawl_date=s["last_crawl_date"],
                    )
                    session.add(rec)
                upserted += 1
            session.commit()
            self.logger.info(
                f"{user_info} Upserted {upserted} LSP summary rows for {start_date.date()} - {end_date.date()}")
            return upserted
        except Exception as e:
            session.rollback()
            self.logger.error(f"{user_info} Error upserting LSP summaries: {e}")
            raise
        finally:
            session.close()

    def get_all_summaries(self, year: int, lsp_id: Optional[int] = None, status: Optional[str] = None):
        """Return all LspSummary row per `lsp_id` between the selected year and month.

        Returns:
            (list_of_dicts, count)
        """
        user_info = self._get_user_info()
        session = self.conn_factory.get_session()
        try:
            query = session.query(
                LspSummary.lsp_id.label("lsp_id"),
                LspSummary.name.label("name"),
                LspSummary.scrape_month.label("scrape_month"),
                LspSummary.scrape_year.label("scrape_year"),
                LspSummary.as_on_month.label("as_on_month"),
                LspSummary.as_on_year.label("as_on_year"),
                LspSummary.total_portfolios.label("total_portfolios"),
                LspSummary.total_amount.label("total_amount"),
                LspSummary.dlg_url.label("dlg_url"),
                LspSummary.total_lenders.label("total_lenders"),
                LspSummary.status.label("status"),
                LspSummary.last_crawl_date.label("last_crawl_date"),
                LspMaster.brand_name.label("brand_name"),
                AuditLog.user_id.label("user_id"),
                AuditLog.auto_manual.label("auto_manual"),
                AuditLog.payload.label("payload")
            ).join(LspMaster, LspSummary.lsp_id == LspMaster.id).outerjoin(
                AuditLog, 
                and_(
                    LspSummary.lsp_id == AuditLog.lsp_id,
                    extract('year', LspSummary.last_crawl_date) == extract('year', AuditLog.log_timestamp),
                    extract('month', LspSummary.last_crawl_date) == extract('month', AuditLog.log_timestamp),
                    extract('day', LspSummary.last_crawl_date) == extract('day', AuditLog.log_timestamp),
                    extract('hour', LspSummary.last_crawl_date) == extract('hour', AuditLog.log_timestamp),
                    extract('minute', LspSummary.last_crawl_date) == extract('minute', AuditLog.log_timestamp)
                )
            )

            query = query.filter(LspSummary.scrape_year == year)

            if lsp_id:
                query = query.filter(LspSummary.lsp_id == lsp_id)

            if status:
                query = query.filter(LspSummary.status == status)

            rows = query.all()
            result = []
            for r in rows:
                result.append(
                    {
                        "lsp_id": r.lsp_id,
                        "name": r.name,
                        "brand_name": r.brand_name,
                        "total_portfolios": r.total_portfolios,
                        "total_amount": float(r.total_amount) if r.total_amount is not None else 0.0,
                        "as_on_year": r.as_on_year,
                        "as_on_month": r.as_on_month,
                        "scrape_year": r.scrape_year,
                        "scrape_month": r.scrape_month,
                        "dlg_url": r.dlg_url,
                        "total_lenders": r.total_lenders,
                        "status": r.status,
                        "last_crawl_date": r.last_crawl_date,
                        "user_id": r.user_id,
                        "auto_manual": r.auto_manual,
                        "payload": r.payload,
                    }
                )
            return result, len(result)
        except Exception as e:
            self.logger.exception(f"{user_info} Error fetching LSP summaries: {e}")
            raise
        finally:
            session.close()

    def get_latest_summary(self, status: Optional[str] = None, lsp_name: Optional[str] = None):
        """Return one LspSummary row using the latest `last_crawl_date` (timestamp included).

        Returns:
            (list_of_dicts, count)
        """
        user_info = self._get_user_info()
        session = self.conn_factory.get_session()
        try:
            # Subquery to rank summaries by last_crawl_date descending for each lsp_id
            subq = (
                session.query(
                    LspSummary.lsp_id.label("lsp_id"),
                    LspSummary.name.label("name"),
                    LspSummary.scrape_month.label("scrape_month"),
                    LspSummary.scrape_year.label("scrape_year"),
                    LspSummary.as_on_month.label("as_on_month"),
                    LspSummary.as_on_year.label("as_on_year"),
                    LspSummary.total_portfolios.label("total_portfolios"),
                    LspSummary.total_amount.label("total_amount"),
                    LspSummary.dlg_url.label("dlg_url"),
                    LspSummary.total_lenders.label("total_lenders"),
                    LspSummary.status.label("status"),
                    LspSummary.last_crawl_date.label("last_crawl_date"),
                    func.row_number()
                    .over(
                        partition_by=LspSummary.lsp_id,
                        order_by=[
                            LspSummary.last_crawl_date.desc(),
                            LspSummary.scrape_year.desc(),
                            LspSummary.scrape_month.desc(),
                        ],
                    )
                    .label("rn"),
                )
                .subquery()
            )

            # Query to select only the top-ranked row for each lsp_id
            query = session.query(subq, LspMaster.brand_name.label("brand_name")).join(
                LspMaster, subq.c.lsp_id == LspMaster.id
            ).filter(subq.c.rn == 1).order_by(subq.c.lsp_id.asc())

            if status is not None:
                query = query.filter(subq.c.status == status)
            
            if lsp_name is not None:
                query = query.filter(subq.c.name.ilike(f"%{lsp_name}%"))

            rows = query.all()
            result = []
            portfolios = 0
            amount = 0
            lenders = 0
            for r in rows:
                portfolios = portfolios + r.total_portfolios
                amt = float(r.total_amount) if r.total_amount is not None else 0.0
                amount = amount + amt
                lenders = lenders + int(r.total_lenders) if r.total_lenders is not None else 0.0
                result.append(
                    {
                        "lsp_id": r.lsp_id,
                        "name": r.name,
                        "brand_name": r.brand_name,
                        "total_portfolios": r.total_portfolios,
                        "total_amount": float(r.total_amount) if r.total_amount is not None else 0.0,
                        "as_on_year": r.as_on_year,
                        "as_on_month": r.as_on_month,
                        "scrape_year": r.scrape_year,
                        "scrape_month": r.scrape_month,
                        "status": r.status,
                        "dlg_url": r.dlg_url,
                        "total_lenders": r.total_lenders,
                        "last_crawl_date": r.last_crawl_date,
                    }
                )
            return result, len(result), portfolios, amount, lenders
        except Exception as e:
            self.logger.exception(f"{user_info} Error fetching LSP summaries: {e}")
            raise
        finally:
            session.close()

    def get_raw_data(self, lsp_id, month, year, page=None, per_page=None):
        user_info = self._get_user_info()
        session = self.conn_factory.get_session()
        try:
            query = session.query(DlgRaw).filter(DlgRaw.lsp_id == lsp_id).order_by(DlgRaw.scrape_timestamp.desc())
            if month is not None:
                query = query.filter(extract('month', DlgRaw.scrape_timestamp) == month)
            if year is not None:
                query = query.filter(extract('year', DlgRaw.scrape_timestamp) == year)

            count = query.count()
            if page and per_page:
                query = query.offset((page - 1) * per_page).limit(per_page)
            rows = query.all()
            result = []
            portfolios = set()
            amount = 0
            unique_lenders = set()
            for r in rows:
                if r.portfolio:
                    portfolios.add(r.portfolio)
                amt = float(r.amount) if r.amount is not None else 0.0
                amount = amount + amt
                if r.lender:
                    unique_lenders.add(r.lender)
                result.append({
                    "id": r.id,
                    "lsp_id": r.lsp_id,
                    "lsp_name": r.lsp_name,
                    "lender": r.lender,
                    "portfolio": r.portfolio,
                    "amount": float(r.amount) if r.amount is not None else 0.0,
                    "as_on_timestamp": r.as_on_timestamp,
                    "scrape_timestamp": r.scrape_timestamp,
                    "dlg_url": r.dlg_url,
                    "complete": r.complete,
                })
            if(len(portfolios) < len(unique_lenders)):
                no_of_portfolios = len(unique_lenders)
            else:
                no_of_portfolios = len(portfolios)
            return result, count, no_of_portfolios, amount, len(unique_lenders)
        except Exception as e:
            self.logger.exception(f"{user_info} Error fetching LSP raw data for lsp_id={lsp_id}: {e}")
            raise
        finally:
            session.close()

    def get_summary_for_graph(self, year: int, lsp_id: Optional[int] = None, status: Optional[str] = None):
        """Return summary data for a given lsp_id and status, aggregated by month_year (e.g. "2023-08")."""
        user_info = self._get_user_info()
        session = self.conn_factory.get_session()
        try:
            query = session.query(
                func.concat(LspSummary.scrape_year, "-", func.lpad(func.cast(LspSummary.scrape_month, String), 2, "0")).label("month_year"),
                func.sum(LspSummary.total_amount).label("total_amount"),
                func.sum(LspSummary.total_portfolios).label("total_portfolios"),
                func.sum(LspSummary.total_lenders).label("total_lenders"),
            )

            query = query.filter(LspSummary.scrape_year == year)

            if lsp_id is not None:
                query = query.filter(LspSummary.lsp_id == lsp_id)
            if status is not None:
                query = query.filter(LspSummary.status == status)

            query = query.group_by("month_year").order_by("month_year")

            rows = query.all()
            result = []
            for r in rows:
                result.append({
                    "month_year": r.month_year,
                    "total_amount": float(r.total_amount) if r.total_amount is not None else 0.0,
                    "total_portfolios": int(r.total_portfolios) if r.total_portfolios is not None else 0,
                    "total_lenders": int(r.total_lenders) if r.total_lenders is not None else 0,
                })
            return result, len(result)
        except Exception as e:
            self.logger.exception(f"{user_info} Error fetching LSP summary for graph: {e}")
            raise
        finally:
            session.close()
