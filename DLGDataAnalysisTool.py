"""Flask entrypoint for DLG scraping and analysis REST API.

Clean architecture entrypoint:
- Application initialization and configuration
- Flask route definitions (thin wrappers)
- All business logic delegated to controllers
"""
import os
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS
from utils.logger_config import logger_method

from General.Controllers.DlgCrawlerController import crawler_bp
from General.Controllers.LSPMasterController import lsp_master_bp
from General.Controllers.AuditLogController import auditlog_bp
from General.Controllers.AuthController import auth_bp
from General.Controllers.ReportsController import reports_bp
from General.Controllers.DashboardController import dashboard_bp

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
            cron_expr = os.getenv("DLG_CRON", "0 * * * *")  # Default: top of every hour
            timezone = os.getenv("DLG_CRON_TZ", "UTC")

            # scheduler = BackgroundScheduler(timezone=timezone)
            # scheduler.add_job(
            #     crawler_controller.run_scrape(),
            #     CronTrigger.from_crontab(cron_expr)
            # )
            # scheduler.start()

            logger.info("Cron scheduler started: {0} ({0})", cron_expr, timezone)

    # Run Flask server
    logger.info("Starting Flask server on {0}:{0}", settings.host, settings.port)
    app.run(host=settings.host, port=settings.port, debug=settings.debug)


if __name__ == "__main__":
    main()
