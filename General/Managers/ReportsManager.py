from typing import Optional, Dict
import datetime as dt
import pandas as pd

from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.DatabaseModels.report_models import Base, LspSummary
from DatabaseOperation.DatabaseModels.master_models import DlgRaw, CrawlStatus
from utils.logger_config import logger_method
from sqlalchemy import func


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
                "amount": r.amount,
                "status": r.complete,
                "as_on_timestamp": r.as_on_timestamp,
                "scrape_timestamp": r.scrape_timestamp,
            })

        df = pd.DataFrame.from_records(records)

        # ensure timestamps are datetimes
        if "as_on_timestamp" in df.columns:
            df["as_on_timestamp"] = pd.to_datetime(df["as_on_timestamp"], errors="coerce")
        df["scrape_timestamp"] = pd.to_datetime(df["scrape_timestamp"], errors="coerce")

        # group by lsp_id and lsp_name
        grouped = df.groupby(["lsp_id", "lsp_name"])

        summaries = []
        for (lsp_id, name), grp in grouped:
            status: CrawlStatus = CrawlStatus.MISSING
            total_amount = 0.0
            total_portfolios = 0

            if grp['status'].notna().any():
                status = CrawlStatus(grp['status'].iloc[0])

            total_amount = float(grp["amount"].fillna(0.0).sum())
            if "portfolio" in grp.columns:
                total_portfolios = int(grp["portfolio"].nunique(dropna=True))
            else:
                total_portfolios = int(grp.shape[0])

            last_scrape = None
            if grp["scrape_timestamp"].notna().any():
                last_scrape = grp["scrape_timestamp"].max()

            last_ason = None
            if grp["as_on_timestamp"].notna().any():
                last_ason = grp["as_on_timestamp"].max()

            scrape_month = int(last_scrape.month)
            scrape_year = int(last_scrape.year)

            # todo fix this:
            # todo: ask what to do in case of partial data when ason date is not available?
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
                "total_amount": total_amount,
                "as_on_year": as_on_year,
                "as_on_month": as_on_month,
                "scrape_year": scrape_year,
                "scrape_month": scrape_month,
                "status": status.value,
                "last_crawl_date": pd.to_datetime(last_scrape).to_pydatetime() if pd.notnull(last_scrape) else None,
            })

        session.close()

        # upsert into DB
        session = self.conn_factory.get_session()
        upserted = 0
        try:
            for s in summaries:
                existing = session.query(LspSummary).filter_by(lsp_id=s["lsp_id"], scrape_year=s["scrape_year"],
                                                               scrape_month=s["scrape_month"]).one_or_none()
                if existing:
                    existing.name = s["name"]
                    existing.total_portfolios = s["total_portfolios"]
                    existing.total_amount = s["total_amount"]
                    existing.as_on_year = s["as_on_year"]
                    existing.as_on_month = s["as_on_month"]
                    existing.status = s["status"]
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
                        status=s["status"],
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

    def get_all_summaries(self, start_year: Optional[int] = None, end_year: Optional[int] = None,
                          start_month: Optional[int] = None, end_month: Optional[int] = None,
                          lsp_id: Optional[int] = None):
        """Return all LspSummary row per `lsp_id` between the selected year and month).

        Returns:
            (list_of_dicts, count)
        """
        user_info = self._get_user_info()
        session = self.conn_factory.get_session()
        try:
            query = session.query(LspSummary)
            if lsp_id:
                query = query.filter(LspSummary.lsp_id == lsp_id)

            query = query.filter(start_year <= LspSummary.scrape_year).filter(
                LspSummary.scrape_year <= end_year).filter(start_month <= LspSummary.scrape_month).filter(
                LspSummary.scrape_month <= end_month)

            rows = query.all()
            result = []
            for r in rows:
                result.append(
                    {
                        "lsp_id": r.lsp_id,
                        "name": r.name,
                        "total_portfolios": r.total_portfolios,
                        "total_amount": float(r.total_amount) if r.total_amount is not None else 0.0,
                        "as_on_year": r.as_on_year,
                        "as_on_month": r.as_on_month,
                        "scrape_year": r.scrape_year,
                        "scrape_month": r.scrape_month,
                        "status": r.status,
                        "last_crawl_date": r.last_crawl_date,
                    }
                )
            return result, len(result)
        except Exception as e:
            self.logger.exception(f"{user_info} Error fetching LSP summaries: {e}")
            raise
        finally:
            session.close()

    def get_latest_summary(self):
        """Return one LspSummary row per `lsp_id` using the latest `last_crawl_date` (timestamp included).

        Returns:
            (list_of_dicts, count)
        """
        user_info = self._get_user_info()
        session = self.conn_factory.get_session()
        try:
            # Subquery to rank summaries by last_crawl_date descending for each lsp_id
            subq = (
                session.query(
                    LspSummary,
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
            query = session.query(subq).filter(subq.c.rn == 1).order_by(subq.c.lsp_id.asc())

            rows = query.all()
            result = []
            for r in rows:
                result.append(
                    {
                        "lsp_id": r.lsp_id,
                        "name": r.name,
                        "total_portfolios": r.total_portfolios,
                        "total_amount": float(r.total_amount) if r.total_amount is not None else 0.0,
                        "as_on_year": r.as_on_year,
                        "as_on_month": r.as_on_month,
                        "scrape_year": r.scrape_year,
                        "scrape_month": r.scrape_month,
                        "status": r.status,
                        "last_crawl_date": r.last_crawl_date,
                    }
                )
            return result, len(result)
        except Exception as e:
            self.logger.exception(f"{user_info} Error fetching LSP summaries: {e}")
            raise
        finally:
            session.close()

    def get_raw_data(self, lsp_id, page=None, per_page=None):
        user_info = self._get_user_info()
        session = self.conn_factory.get_session()
        try:
            query = session.query(DlgRaw).filter(DlgRaw.lsp_id == lsp_id).order_by(DlgRaw.scrape_timestamp.desc())
            count = query.count()
            if page and per_page:
                query = query.offset((page - 1) * per_page).limit(per_page)
            rows = query.all()
            result = []
            for r in rows:
                result.append({
                    "lsp_id": r.lsp_id,
                    "lsp_name": r.lsp_name,
                    "lender": r.lender,
                    "portfolio": r.portfolio,
                    "amount": float(r.amount) if r.amount is not None else 0.0,
                    "as_on_timestamp": r.as_on_timestamp,
                    "scrape_timestamp": r.scrape_timestamp,
                    "complete": r.complete,
                })
            return result, count
        except Exception as e:
            self.logger.exception(f"{user_info} Error fetching LSP raw data for lsp_id={lsp_id}: {e}")
            raise
        finally:
            session.close()
