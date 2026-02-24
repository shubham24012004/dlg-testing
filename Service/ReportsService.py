from typing import Optional, Any, Dict

from utils.logger_config import logger_method
from Managers.ReportsManager import ReportsManager
from Service.AuditLogService import AuditLogService
from utils.constants import AuditAction


class ReportsService:
    """Service wrapper around ReportsManager that adds audit logging."""

    def __init__(self, user_claims: Optional[Dict[str, Any]] = None):
        self.logger = logger_method(__name__)
        self.user_claims = user_claims
        self.reports_manager = ReportsManager(user_claims=self.user_claims)
        self.auditlog_service = AuditLogService(self.user_claims)

    def run_lsp_summarize(self, start_date, end_date) -> int:
        """Run LSP summarization and record audit logs including `user_claims` in payload.

        Returns the number of summary rows upserted.
        """
        user_info = f"[User: {self.user_claims.get('username') if self.user_claims else 'system'}, Role: {self.user_claims.get('role') if self.user_claims else 'unknown'}]"
        self.logger.info(f"{user_info} Starting LSP summarization for {start_date} - {end_date}")

        try:
            upserted = self.reports_manager.lsp_summarize(start_date, end_date)

            user_id = self.user_claims.get('username') if self.user_claims else "system"
            payload = {
                "status": "Success",
                "upserted": upserted,
                "start_date": str(start_date),
                "end_date": str(end_date),
            }
            self.auditlog_service.record(
                self.auditlog_service.build(
                    lsp_id=None,
                    action_taken=AuditAction.LSP_SUMMARY,
                    auto_manual="manual",
                    user_id=user_id,
                    payload=payload,
                )
            )
            self.logger.info(f"{user_info} Completed LSP summarization: upserted={upserted}")
            return upserted
        except Exception as exc:
            user_id = self.user_claims.get('username') if self.user_claims else "system"
            payload = {
                "status": "Exception",
                "details": str(exc)[:1000],
                "start_date": str(start_date),
                "end_date": str(end_date),
            }
            try:
                self.auditlog_service.record(
                    self.auditlog_service.build(
                        lsp_id=None,
                        action_taken=AuditAction.LSP_SUMMARY,
                        auto_manual="manual",
                        user_id=user_id,
                        payload=payload,
                    )
                )
            except Exception as ex:
                self.logger.exception(f"{user_info} Failed recording audit log for summarization failure")

            self.logger.exception(f"{user_info} LSP summarization failed: {exc}")
            raise

    def get_latest_summary(self):
        """Fetch LSP summaries from ReportsManager filtered by last_crawl_date.

        Returns:
            (list_of_dicts, count)
        """
        user_info = f"[User: {self.user_claims.get('username') if self.user_claims else 'system'}, Role: {self.user_claims.get('role') if self.user_claims else 'unknown'}]"
        try:
            result, count, portfolios, amount, lenders = self.reports_manager.get_latest_summary()
            self.logger.info(f"{user_info} Fetched {count} summary rows")
            return result, count, portfolios, amount, lenders
        except Exception as exc:
            self.logger.exception(f"{user_info} Error fetching summaries: {exc}")
            raise

    def get_all_summaries(self, start_year: Optional[int] = None, end_year: Optional[int] = None,
                          start_month: Optional[int] = None, end_month: Optional[int] = None,
                          lsp_id: Optional[int] = None):
        """Fetch LSP summaries from ReportsManager filtered by last_crawl_date.

        Returns:
            (list_of_dicts, count)
        """
        user_info = f"[User: {self.user_claims.get('username') if self.user_claims else 'system'}, Role: {self.user_claims.get('role') if self.user_claims else 'unknown'}]"
        try:
            result, count = self.reports_manager.get_all_summaries(start_year=start_year,
                                                                   end_year=end_year,
                                                                   start_month=start_month,
                                                                   end_month=end_month,
                                                                   lsp_id=lsp_id)
            self.logger.info(f"{user_info} Fetched {count} summary rows")
            return result, count
        except Exception as exc:
            self.logger.exception(f"{user_info} Error fetching summaries: {exc}")
            raise
    
    def get_raw_data(self, lsp_id: int, month: Optional[int] = None, year: Optional[int] = None):
        """Fetch LSP raw data from ReportsManager for a specific LSP ID.

        Returns:
            (list_of_dicts, count)
        """
        user_info = f"[User: {self.user_claims.get('username') if self.user_claims else 'system'}, Role: {self.user_claims.get('role') if self.user_claims else 'unknown'}]"
        try:
            result, count, portfolio_count, amount, lenders_count = self.reports_manager.get_raw_data(lsp_id, month=month, year=year)
            self.logger.info(f"{user_info} Fetched {count} raw rows for LSP ID: {lsp_id}")
            return result, count, portfolio_count, amount, lenders_count
        except Exception as exc:
            self.logger.exception(f"{user_info} Error fetching raw data for LSP ID {lsp_id}: {exc}")
            raise

    def get_summary_for_graph(self, lsp_id: int, start_year: Optional[int] = None, end_year: Optional[int] = None,
                              start_month: Optional[int] = None, end_month: Optional[int] = None, status: Optional[str] = None):
        """Fetch LSP summary data for graphing from ReportsManager for a specific LSP ID.

        Returns:
            (list_of_dicts, count)
        """
        user_info = f"[User: {self.user_claims.get('username') if self.user_claims else 'system'}, Role: {self.user_claims.get('role') if self.user_claims else 'unknown'}]"
        try:
            result, count = self.reports_manager.get_summary_for_graph(lsp_id, start_year=start_year, end_year=end_year,
                                                                       start_month=start_month, end_month=end_month, status=status)
            self.logger.info(f"{user_info} Fetched {count} summary rows for graphing for LSP ID: {lsp_id}")
            return result, count
        except Exception as exc:
            self.logger.exception(f"{user_info} Error fetching summary for graph for LSP ID {lsp_id}: {exc}")
            raise