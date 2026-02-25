"""Flask entrypoint for DLG scraping and analysis REST API.

Clean architecture entrypoint:
- Application initialization and configuration
- Flask route definitions (thin wrappers)
- All business logic delegated to controllers
"""
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS
from utils.logger_config import logger_method

from Controllers.DlgCrawlerController import crawler_bp, run_scrape
from Controllers.LSPMasterController import lsp_master_bp
from Controllers.AuditLogController import auditlog_bp
from Controllers.AuthController import auth_bp
from Controllers.ReportsController import reports_bp
from Controllers.DashboardController import dashboard_bp
from Controllers.UserController import user_bp
from Controllers.DlgRawController import dlg_raw_bp
from Service.ReportsService import ReportsService

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    APSCHEDULER_AVAILABLE = True
except Exception:
    APSCHEDULER_AVAILABLE = False

# Load environment variables
load_dotenv()

logger = logger_method(__name__)


@dataclass(slots=True)
class AppSettings:
    """HTTP server configuration."""

    host: str = os.getenv("DLG_FLASK_HOST", "0.0.0.0")
    port: int = int(os.getenv("DLG_FLASK_PORT", "5000"))
    debug: bool = os.getenv("DLG_FLASK_DEBUG", "0") in {"1", "true", "True"}


# Application configuration
settings = AppSettings()
app = Flask(__name__)

CORS(app)
app.register_blueprint(auth_bp)
app.register_blueprint(lsp_master_bp)
app.register_blueprint(auditlog_bp)
app.register_blueprint(crawler_bp)
app.register_blueprint(reports_bp)
app.register_blueprint(dashboard_bp)
app.register_blueprint(user_bp)
app.register_blueprint(dlg_raw_bp)


# ==================== Cron Tasks ====================

def cron_run_all_scrapes() -> None:
    """Cron task: trigger scrape for all active LSPs (no specific lsp_id)."""
    logger.info("Cron: starting all-LSP scrape")
    try:
        count = run_scrape(lsp_id=0, user_claims=None)
        logger.info(f"Cron: all-LSP scrape completed, {count} sources scraped")
    except Exception as exc:
        logger.error(f"Cron: all-LSP scrape failed: {exc}", exc_info=True)


def cron_run_lsp_summarize() -> None:
    """Cron task: run LSP summarization for the default date window
    (15th of previous month → 15th of current month).
    """
    today = datetime.now()
    start_dt = today - timedelta(days=30)
    end_dt = today
    logger.info(f"Cron: starting LSP summarization {start_dt.date()} → {end_dt.date()}")
    try:
        reports_service = ReportsService(user_claims=None)
        upserted = reports_service.run_lsp_summarize(start_dt, end_dt)
        logger.info(f"Cron: LSP summarization completed, {upserted} rows upserted")
    except Exception as exc:
        logger.error(f"Cron: LSP summarization failed: {exc}", exc_info=True)


# ==================== Health & Utility Endpoints ====================

@app.get("/healthz")
def healthcheck() -> Any:
    return jsonify({"status": "ok", "message": "OK"})


def main() -> None:
    # db_path = os.getenv("DLG_SQLITE_PATH", "dlg_analysis.db")
    #
    # logger.info("Application initialized with database: {0}", db_path)

    # Setup cron job scheduler if enabled
    if os.getenv("DLG_CRON_ENABLED", "0") in {"1", "true", "True"}:
        if not APSCHEDULER_AVAILABLE:
            raise RuntimeError("APScheduler not installed; add it to requirements.txt")

        # Only start scheduler once (avoid Flask reloader double-start)
        if not settings.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            scrape_cron = os.getenv("DLG_CRON", "0 0 * * *")          # Default: top of every hour
            summarize_cron = os.getenv("DLG_SUMMARIZE_CRON", "0 1 * * *")  # Default: 01:00 on the 15th of each month
            timezone = os.getenv("DLG_CRON_TZ", "UTC")

            scheduler = BackgroundScheduler(timezone=timezone)
            scheduler.add_job(
                cron_run_all_scrapes,
                CronTrigger.from_crontab(scrape_cron, timezone=timezone)
            )
            scheduler.add_job(
                cron_run_lsp_summarize,
                CronTrigger.from_crontab(summarize_cron, timezone=timezone)
            )
            scheduler.start()

            logger.info(
                f"Cron scheduler started: scrape='{scrape_cron}', summarize='{summarize_cron}' (tz={timezone})"
            )

    # Run Flask server
    logger.info("Starting Flask server on {0}:{0}", settings.host, settings.port)
    app.run(host=settings.host, port=settings.port, debug=settings.debug)


if __name__ == "__main__":
    main()
