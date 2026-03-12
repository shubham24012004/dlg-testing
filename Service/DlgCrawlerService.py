import datetime as dt
from utils.logger_config import logger_method
from typing import Any, Dict, List, Optional, Tuple
from utils.simple_ocr_extractor import extract_simple
from Service.AuditLogService import AuditLogService
from Managers.DlgCrawlerManager import DlgCrawlerManager
from DatabaseOperation.DatabaseModels.master_models import FetchResult, LspMaster, DlgRaw
from utils.constants import AuditAction, CrawlStatus

from Managers.LspMasterManager import LspMasterManager
from utils.utils import (
    extract_dlg_from_plain_text,
    extract_finsall_grand_total,
    extract_from_html_tables,
    extract_from_pdf,
    load_rules,
    looks_like_pdf,
    normalize_rows,
    parse_date_any,
    fetch_with_requests,
    fetch_with_playwright,
    render_url_to_pdf,
    subtract_months,
    parse_month_year_token,
    build_replacement_token,
    head_checks_pdf,
)

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


class DlgCrawlerService:
    """Coordinates fetching, parsing, and persistence for DLG disclosures."""

    def __init__(self, user_claims: Optional[Dict[str, Any]] = None):
        self.logger = logger_method(__name__)
        self.user_claims = user_claims
        self.crawler_manager = DlgCrawlerManager(user_claims=user_claims)
        self.auditlog_service = AuditLogService(user_claims)

    def run_scrape_sources(self, sources: List[LspMaster]) -> None:
        for source in sources:
            # Promote T-2 month-based URL to T-1 before scraping if a newer PDF exists
            self._maybe_promote_to_t1(source)
            scrape_started_at = dt.datetime.now(tz=dt.timezone.utc)
            try:
                status, fetch_mode, content_type, normalized_rows, error = self.scrape_one(source)
                self.persist_rows(status, normalized_rows, source, scrape_started_at)
                user_id = self.user_claims.get('username') if self.user_claims else "system"
                self.auditlog_service.record(
                    self.auditlog_service.build(
                        lsp_id=source.id,
                        action_taken=AuditAction.CRAWL,
                        auto_manual="auto",
                        user_id=user_id,
                        payload={"status": status.value, "details": error, "ts": scrape_started_at.isoformat()}
                    )
                )
                self.logger.info(f"[OK] {source.name} -> {status.value}  -> {error}")
            except Exception as exc:
                self.persist_error(source, scrape_started_at)
                user_id = self.user_claims.get('username') if self.user_claims else "system"
                self.auditlog_service.record(
                    self.auditlog_service.build(
                        lsp_id=source.id,
                        action_taken=AuditAction.CRAWL,
                        auto_manual="auto",
                        user_id=user_id,
                        payload={"status": "Error", "details": str(exc)[:200], "ts": scrape_started_at.isoformat()}
                    )
                )
                self.logger.error(f"[ERR logging Audit Log] {source.name} -> Error ({str(exc)[:120]})")

    def scrape_one(self, source: LspMaster) -> Tuple[
        CrawlStatus, Optional[str], Optional[str], List[Dict[str, Any]], str]:
        scrape_ts = dt.datetime.now(tz=dt.timezone.utc)
        rules = load_rules(source.rules_json) if source.rules_json else {}
        pre_click_js = rules.get("pre_click_js")
        playwright_wait_ms = self._coerce_int(rules.get("playwright_wait_ms")) or 0
        ocr_rules = rules.get("ocr") or {}
        simple_cfg = ocr_rules.get("simple") if isinstance(ocr_rules.get("simple"), dict) else ocr_rules

        if not source.dlg_url:
            return CrawlStatus.MISSING, None, None, [], "Missing DLG URL"
        try:
            fetch = self._execute_fetch(source, pre_click_js, wait_ms=playwright_wait_ms)  # T&C

        except Exception as exc:
            return CrawlStatus.ERROR, None, None, [], str(exc)

        # For OCR with HTML→PDF rendering, extract page-level values (like dates) from HTML before rendering
        html_page_values = {}
        if source.parse_hint == "ocr_simple" and not looks_like_pdf(fetch):
            render_pdf = bool(simple_cfg.get("render_pdf"))
            if render_pdf:
                # Extract date/lender info from HTML before it's converted to PDF
                from utils.utils import page_level_values
                try:
                    html_page_values = page_level_values(fetch, rules)

                    fetch = render_url_to_pdf(
                        url=source.dlg_url,
                        timeout_ms=self._coerce_int(simple_cfg.get("render_timeout_ms")) or 120_000,
                        wait_ms=self._coerce_int(simple_cfg.get("render_wait_ms")) or 0,
                        wait_until=simple_cfg.get("render_wait_until") or "networkidle",
                        pre_click_js=pre_click_js)
                except Exception as exc:
                    return CrawlStatus.ERROR, None, None, [], f"OCR with HTML→PDF rendering failed: {exc}"
            else:
                raise RuntimeError(
                    "parse_hint=ocr_simple requires a PDF disclosure; set ocr.render_pdf=true to render HTML to PDF"
                )

        raw_rows, parse_error = self._parse_rows(
            source=source,
            fetch=fetch,
            rules=rules,
            scrape_ts=scrape_ts,
            html_page_values=html_page_values,
        )

        if not raw_rows and source.name.lower().startswith("finsall"):
            raw_rows = extract_finsall_grand_total(fetch, source.name, scrape_ts, rules)

        crawl_status, normalized, error = normalize_rows(
            raw_rows=raw_rows,
            fetch=fetch,
            lsp_name=source.name,
            scrape_ts=scrape_ts,
            rules_json=source.rules_json,
        )
        final_error = ""
        if crawl_status in {CrawlStatus.MISSING, CrawlStatus.ERROR, CrawlStatus.NO_DATA}:
            final_error = f"error during data extraction/normalization: {error}"
        if parse_error:
            final_error = final_error + f"error during data fetch/parsing: {parse_error}"

        return crawl_status, fetch.fetch_mode_used, fetch.content_type, normalized, final_error

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def persist_rows(
            self,
            status: CrawlStatus,
            normalized_rows: List[Dict[str, Any]],
            source: LspMaster,
            scrape_ts: dt.datetime,
    ) -> None:
        # Save actual data for COMPLETED, PARTIAL, and STALE (data exists but date missing)
        if status in {CrawlStatus.COMPLETED, CrawlStatus.PARTIAL, CrawlStatus.STALE} and normalized_rows:
            dlg_rows = [self.dlg_raw_from_dict(row, status.value) for row in normalized_rows]
            for dlg_row in dlg_rows:
                dlg_row.lsp_id = source.id
                dlg_row.lsp_name = source.name
                dlg_row.dlg_url = source.dlg_url
            self.crawler_manager.append(dlg_rows)
            return

        # For ERROR, MISSING, NO_DATA, or when no rows extracted, create dummy row
        # if status in {CrawlStatus.MISSING, CrawlStatus.ERROR, CrawlStatus.NO_DATA}:
        else:
            row = DlgRaw(
                lsp_id=source.id,
                lsp_name=source.name,
                lender=None,
                portfolio=None,
                amount=None,
                as_on_timestamp=None,
                scrape_timestamp=scrape_ts,
                complete=status.value,
                dlg_url=source.dlg_url if source.dlg_url is not None else "NA"
            )
            self.crawler_manager.append([row])

    def persist_error(self, source: LspMaster, scrape_ts: dt.datetime) -> None:
        row = DlgRaw(
            lsp_name=source.name,
            lender=None,
            portfolio=None,
            amount=None,
            as_on_timestamp=None,
            scrape_timestamp=scrape_ts,
            complete=CrawlStatus.ERROR.value,
            lsp_id=source.id,
            dlg_url=source.dlg_url if source.dlg_url is not None else "NA"
        )
        self.crawler_manager.append([row])

    @staticmethod
    def dlg_raw_from_dict(data: Dict[str, Any], status: str) -> DlgRaw:
        return DlgRaw(
            lender=data.get("Lender"),
            portfolio=data.get("Portfolio"),
            amount=data.get("Amount"),
            as_on_timestamp=data.get("AsOnTimestamp"),
            scrape_timestamp=data.get("ScrapeTimestamp"),
            complete=status
        )

    # ------------------------------------------------------------------
    # T-1 URL promotion
    # ------------------------------------------------------------------
    def _maybe_promote_to_t1(self, source: LspMaster) -> None:
        """If source.dlg_url contains a month token at T-2, check whether
        the equivalent T-1 URL exists as a valid PDF.  If so, update
        source.dlg_url in-memory *and* persist the new URL to lsp_master
        so the crawl (and all future crawls) use the fresh link.

        The actual data extraction/persistence happens through the normal
        crawl pipeline — no special casing needed here.
        """
        if not source.dlg_url:
            return
        parsed = parse_month_year_token(source.dlg_url)
        if not parsed:
            return
        year, month, token, match = parsed
        if month is None:
            return

        now = dt.datetime.now()
        t_minus_2 = subtract_months(now, 2)
        if year != t_minus_2.year or month != t_minus_2.month:
            return

        t_minus_1 = subtract_months(now, 1)
        new_token = build_replacement_token(token, match, t_minus_1.year, t_minus_1.month)
        candidate_url = source.dlg_url.replace(token, new_token, 1)

        if candidate_url == source.dlg_url:
            return

        self.logger.info(
            f"[T-1 check] {source.name}: candidate URL {candidate_url}"
        )

        if not head_checks_pdf(candidate_url):
            self.logger.info(f"[T-1 check] {source.name}: candidate not a valid PDF — keeping current URL")
            return

        # Update in-memory so this crawl uses the new URL
        source.dlg_url = candidate_url

        # Persist to lsp_master so future crawls also use it
        try:
            lsp_mgr = LspMasterManager(self.user_claims)
            lm_update = LspMaster()
            lm_update.id = source.id
            lm_update.dlg_url = candidate_url
            lm_update.active = source.active
            lsp_mgr.update(lm_update)
            self.logger.info(
                f"[T-1 check] {source.name}: promoted dlg_url to {candidate_url}"
            )
        except Exception as exc:
            self.logger.warning(
                f"[T-1 check] {source.name}: in-memory URL updated but DB update failed: {exc}"
            )

    # ------------------------------------------------------------------
    # Fetching/parsing helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _execute_fetch(source: LspMaster,
                       pre_click_js: Optional[str],
                       wait_ms: int = 0,
                       ) -> FetchResult:
        fetch_hint = (source.fetch_hint or "auto").lower()
        if fetch_hint == "playwright":
            return fetch_with_playwright(source.dlg_url, pre_click_js=pre_click_js, wait_ms=wait_ms)
        return fetch_with_requests(source.dlg_url)

    def _parse_rows(self,
                    source: LspMaster,
                    fetch: FetchResult,
                    rules: Dict[str, Any],
                    scrape_ts: dt.datetime,
                    html_page_values: Optional[Dict[str, Any]] = None,
                    ) -> Tuple[List[Dict[str, Any]], str]:
        parse_hint = (source.parse_hint or "auto").lower()
        try:
            if parse_hint == "plain_text":
                return extract_dlg_from_plain_text(fetch.body, lsp_name=source.name, scrape_ts=scrape_ts, rules_json=source.rules_json), ""
            if parse_hint == "ocr_simple":
                return self._extract_rows_with_simple_ocr(fetch, source.name, scrape_ts, rules, html_page_values or {}), ""
            if parse_hint == "pdf_table" or looks_like_pdf(fetch):
                # Use extract_from_pdf which now has a per-LSP conditional block
                return extract_from_pdf(fetch, lsp_name=source.name, rules=rules), ""
            if parse_hint == "html_table":
                return extract_from_html_tables(fetch, table_index=rules.get("table_index")), "None"

            # auto
            if looks_like_pdf(fetch):
                return extract_from_pdf(fetch), ""

            rows = extract_from_html_tables(fetch, table_index=rules.get("table_index"))
            if not rows and PLAYWRIGHT_AVAILABLE and fetch.fetch_mode_used != "playwright":
                fetch_pw = fetch_with_playwright(source.dlg_url, pre_click_js=rules.get("pre_click_js"),
                                                 wait_ms=rules.get("playwright_wait_ms") or 0)
                rows = extract_from_html_tables(fetch_pw, table_index=rules.get("table_index"))
            return rows, ""
        except Exception as exc:
            self.logger.error(f"Error parsing rows for {source.name} with parse_hint={parse_hint}: {exc}")
            error = f"Error parsing rows for {source.name} with parse_hint={parse_hint}: {exc}"
            return [], error

    # ------------------------------------------------------------------
    # Playwright + OCR helpers (mostly lifted from the legacy script)
    # ------------------------------------------------------------------

    @staticmethod
    def _coerce_float(val: Optional[Any]) -> Optional[float]:
        if val is None or val == "":
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_int(val: Optional[Any]) -> Optional[int]:
        if val is None or val == "":
            return None
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    def _extract_rows_with_simple_ocr(
            self,
            fetch: FetchResult,
            lsp_name: str,
            scrape_ts: dt.datetime,
            rules: Dict[str, Any],
            html_page_values: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        try:
            if not looks_like_pdf(fetch):
                raise RuntimeError("parse_hint=ocr_simple requires a PDF disclosure")

            ocr_rules = rules.get("ocr") or {}
            simple_cfg = ocr_rules.get("simple") if isinstance(ocr_rules.get("simple"), dict) else ocr_rules
            if not simple_cfg:
                raise RuntimeError("Missing 'ocr' configuration for parse_hint=ocr_simple")

            method = (simple_cfg.get("method") or "simple").lower()
            if method != "simple":
                raise RuntimeError(f"Unsupported OCR method '{method}'")

            resolution = self._coerce_int(simple_cfg.get("resolution")) or 300
            min_conf = self._coerce_int(simple_cfg.get("min_conf")) or 60
            slice_count = self._coerce_int(simple_cfg.get("slice_count")) or 0
            crop_top = self._coerce_float(simple_cfg.get("crop_top_pct"))
            crop_bottom = self._coerce_float(simple_cfg.get("crop_bottom_pct"))
            lang = simple_cfg.get("lang", "eng")
            amount_unit = (simple_cfg.get("amount_unit") or "rupees").lower()

            records = extract_simple(
                pdf_path=fetch.body,
                resolution=resolution,
                lang=lang,
                min_conf=min_conf,
                dump_text=None,
                crop_top=crop_top,
                crop_bottom=crop_bottom,
                slice_count=slice_count,
            )

            field_map = rules.get("field_map") or {}
            as_on_cfg = field_map.get("as_on")
            as_on_dt = None

            # Try HTML page-level values first (extracted before render_pdf)
            if html_page_values.get("as_on"):
                as_on_dt = parse_date_any(html_page_values["as_on"])
            # Then try field_map config
            elif isinstance(as_on_cfg, dict):
                # Try constant first
                if "constant" in as_on_cfg:
                    as_on_dt = parse_date_any(as_on_cfg.get("constant"))
                # Try fallback if no constant
                elif "fallback" in as_on_cfg:
                    fallback_type = as_on_cfg["fallback"]
                    if fallback_type == "previous_month_end":
                        from utils.utils import calculate_previous_month_end
                        as_on_dt = calculate_previous_month_end(scrape_ts)
                    elif fallback_type == "previous_quarter_end":
                        from utils.utils import calculate_previous_quarter_end
                        as_on_dt = calculate_previous_quarter_end(scrape_ts)
            elif isinstance(as_on_cfg, str):
                as_on_dt = parse_date_any(as_on_cfg)

            lender_constant = None
            lender_cfg = field_map.get("lender")
            if isinstance(lender_cfg, dict) and lender_cfg.get("constant"):
                lender_constant = lender_cfg.get("constant")

            def to_crores(raw_amount: float) -> float:
                if amount_unit.startswith("crore"):
                    return raw_amount
                if amount_unit.startswith("lakh"):
                    return raw_amount / 100.0
                return raw_amount / 10_000_000.0

            rows: List[Dict[str, Any]] = []
            for record in records:
                portfolio = record.portfolio_hint or None
                if not portfolio:
                    continue
                amount_crores = round(to_crores(record.amount), 4)
                rows.append(
                    {
                        "LSP Name": lsp_name,
                        "Lender": lender_constant,
                        "Portfolio": portfolio,
                        "Amount": amount_crores,
                        "AsOnTimestamp": as_on_dt,
                        "ScrapeTimestamp": scrape_ts,
                    }
                )
            return rows
        except Exception as exc:
            self.logger.error(f"Error in OCR extraction for {lsp_name}: {exc}")
            raise RuntimeError(f"Error in OCR extraction for {lsp_name}: {exc}")
