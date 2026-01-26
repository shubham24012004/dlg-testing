import json
import datetime as dt
from utils.logger_config import logger_method
from typing import Any, Dict, List, Optional, Tuple
from utils.simple_ocr_extractor import extract_simple
from General.Service.AuditLogService import AuditLogService
from General.Managers.DlgCrawlerManager import DlgCrawlerManager
from DatabaseOperation.DatabaseModels.orm_models import FetchResult, LspMaster, DlgRaw, AuditAction

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
    render_url_to_pdf
)

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except Exception:
    PLAYWRIGHT_AVAILABLE = False


class DlgCrawlerService:
    """Coordinates fetching, parsing, and persistence for DLG disclosures."""

    def __init__(self):
        self.logger = logger_method(__name__)
        self.crawler_manager = DlgCrawlerManager()
        self.auditlog_service = AuditLogService()

    def run_scrape_sources(self, sources: List[LspMaster]) -> None:
        for source in sources:
            scrape_started_at = dt.datetime.utcnow()
            try:
                status, *_rest, normalized_rows = self.scrape_one(source)
                self.persist_rows(status, normalized_rows, source, scrape_started_at)
                self.auditlog_service.audit_manager.record(
                    self.auditlog_service.audit_manager.build(
                        lsp_id=source.lsp_id,
                        action_taken=AuditAction.CRAWL,
                        auto_manual="auto",
                        user_id="system",
                        payload=json.dumps({"status": status, "details": None, "ts": scrape_started_at.isoformat()}),
                    )
                )
                self.logger.info(f"[OK] {source.lsp_name} -> {status}")
            except Exception as exc:  # pragma: no cover - operational safety
                self.persist_error(source, scrape_started_at)
                self.auditlog_service.audit_manager.record(
                    self.auditlog_service.audit_manager.build(
                        lsp_id=source.lsp_id,
                        action_taken=AuditAction.CRAWL,
                        auto_manual="auto",
                        user_id="system",
                        payload=json.dumps(
                            {"status": "Error", "details": str(exc)[:200], "ts": scrape_started_at.isoformat()}),
                    )
                )
                self.logger.error(f"[ERR] {source.lsp_name} -> Error ({str(exc)[:120]})")

    def scrape_one(self, source: LspMaster) -> Tuple[str, Optional[str], Optional[str], List[Dict[str, Any]]]:
        scrape_ts = dt.datetime.utcnow()
        rules = load_rules(source.rules_json) if source.rules_json else {}
        pre_click_js = rules.get("pre_click_js")
        ocr_rules = rules.get("ocr") or {}
        simple_cfg = ocr_rules.get("simple") if isinstance(ocr_rules.get("simple"), dict) else ocr_rules

        fetch = self._execute_fetch(source, pre_click_js)

        if source.parse_hint == "ocr_simple" and not looks_like_pdf(fetch):
            render_pdf = bool(simple_cfg.get("render_pdf"))
            if render_pdf:
                fetch = render_url_to_pdf(
                    url=source.disclosure_url,
                    timeout_ms=self._coerce_int(simple_cfg.get("render_timeout_ms")) or 120_000,
                    wait_ms=self._coerce_int(simple_cfg.get("render_wait_ms")) or 0,
                    wait_until=simple_cfg.get("render_wait_until") or "networkidle",
                    pre_click_js=pre_click_js)
            else:
                raise RuntimeError(
                    "parse_hint=ocr_simple requires a PDF disclosure; set ocr.render_pdf=true to render HTML to PDF"
                )

        raw_rows = self._parse_rows(
            source=source,
            fetch=fetch,
            rules=rules,
            scrape_ts=scrape_ts,
        )

        if not raw_rows and source.lsp_name.lower().startswith("finsall"):
            raw_rows = extract_finsall_grand_total(fetch, source.lsp_name, scrape_ts, rules)

        normalized, partial_flag = normalize_rows(
            raw_rows=raw_rows,
            fetch=fetch,
            lsp_name=source.lsp_name,
            scrape_ts=scrape_ts,
            rules_json=source.rules_json,
        )

        if partial_flag:
            return "Partial", fetch.fetch_mode_used, fetch.content_type, normalized
        if not partial_flag:
            return "Completed", fetch.fetch_mode_used, fetch.content_type, normalized
        return "Missing", fetch.fetch_mode_used, fetch.content_type, []

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def persist_rows(
            self,
            status: str,
            normalized_rows: List[Dict[str, Any]],
            source: LspMaster,
            scrape_ts: dt.datetime,
    ) -> None:
        if status in {"Completed", "Partial"}:
            dlg_rows = [self.dlg_raw_from_dict(row, status) for row in normalized_rows]
            for dlg_row in dlg_rows:
                dlg_row.lsp_id = source.lsp_id
            self.crawler_manager.append(dlg_rows)
            return

        if status == "Missing":
            row = DlgRaw(
                lsp_name=source.lsp_name,
                lender=None,
                portfolio=None,
                amount=None,
                as_on_timestamp=None,
                scrape_timestamp=scrape_ts,
                complete="Missing",
                lsp_id=(source.lsp_id or source.lsp_name),
            )
            self.crawler_manager.append([row])

    def persist_error(self, source: LspMaster, scrape_ts: dt.datetime) -> None:
        row = DlgRaw(
            lsp_name=source.lsp_name,
            lender=None,
            portfolio=None,
            amount=None,
            as_on_timestamp=None,
            scrape_timestamp=scrape_ts,
            complete="Error",
            lsp_id=(source.lsp_id or source.lsp_name),
        )
        self.crawler_manager.append([row])

    @staticmethod
    def dlg_raw_from_dict(data: Dict[str, Any], status: str) -> DlgRaw:
        return DlgRaw(
            lsp_name=data.get("lsp_name"),
            lender=data.get("lender"),
            portfolio=data.get("portfolio"),
            amount=data.get("amount"),
            as_on_timestamp=data.get("as_on_timestamp"),
            scrape_timestamp=data.get("scrape_timestamp"),
            complete=status
        )

    # ------------------------------------------------------------------
    # Fetching/parsing helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _execute_fetch(source: LspMaster,
                       pre_click_js: Optional[str],
                       ) -> FetchResult:
        fetch_hint = (source.fetch_hint or "auto").lower()
        if fetch_hint == "playwright":
            return fetch_with_playwright(source.disclosure_url, pre_click_js=pre_click_js)
        return fetch_with_requests(source.disclosure_url)

    def _parse_rows(self,
                    source: LspMaster,
                    fetch: FetchResult,
                    rules: Dict[str, Any],
                    scrape_ts: dt.datetime,
                    ) -> List[Dict[str, Any]]:
        parse_hint = (source.parse_hint or "auto").lower()
        if parse_hint == "plain_text":
            return extract_dlg_from_plain_text(fetch.body, lsp_name=source.lsp_name, scrape_ts=scrape_ts,
                                               rules_json=source.rules_json)
        if parse_hint == "ocr_simple":
            return self._extract_rows_with_simple_ocr(fetch, source.lsp_name, scrape_ts, rules)
        if parse_hint == "pdf_table" or looks_like_pdf(fetch):
            return extract_from_pdf(fetch)
        if parse_hint == "html_table":
            return extract_from_html_tables(fetch)

        # auto
        if looks_like_pdf(fetch):
            return extract_from_pdf(fetch)

        rows = extract_from_html_tables(fetch)
        if not rows and PLAYWRIGHT_AVAILABLE and fetch.fetch_mode_used != "playwright":
            fetch_pw = fetch_with_playwright(source.disclosure_url, pre_click_js=rules.get("pre_click_js"))
            rows = extract_from_html_tables(fetch_pw)
        return rows

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
    ) -> List[Dict[str, Any]]:
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
        if isinstance(as_on_cfg, dict):
            as_on_dt = parse_date_any(as_on_cfg.get("constant"))
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
