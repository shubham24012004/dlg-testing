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
from flask import Flask, jsonify, request
from utils.logger_config import logger_method

from General.Controllers.DlgCrawlerController import DlgCrawlerController
from General.Controllers.LSPMasterController import LSPMasterController
from General.Controllers.AuditLogController import AuditLogController

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

crawler_controller = None
lsp_master_controller = None
audit_controller = None

# ==================== Health & Utility Endpoints ====================

@app.get("/healthz")
def healthcheck() -> Any:
    return jsonify({"status": "ok", "message": "OK"})


@app.post("/scrape")
def trigger_scrape() -> Any:
    return jsonify(*crawler_controller.handle_trigger_scrape(request, crawler_controller))


# ==================== LspMaster CRUD Endpoints ====================

@app.post("/api/lsp_master")
def api_upsert_lsp_master() -> Any:
    return jsonify(*lsp_master_controller.handle_upsert_lsp_master(request))


@app.get("/api/lsp_master")
def api_list_lsp_master() -> Any:
    return jsonify(*lsp_master_controller.handle_list_lsp_master(request))


@app.get("/api/lsp_master/<int:id>")
def api_get_lsp_master(lsp_id: int) -> Any:
    return jsonify(*lsp_master_controller.handle_get_lsp_master(lsp_id))


@app.put("/api/lsp_master/<int:id>")
def api_update_lsp_master(lsp_id: int) -> Any:
    return jsonify(*lsp_master_controller.handle_update_lsp_master(lsp_id, request))


@app.delete("/api/lsp_master/<lsp_id>")
def api_delete_lsp_master(lsp_id: str) -> Any:
    return jsonify(*lsp_master_controller.handle_delete_lsp_master(lsp_id))


# ==================== AuditLog CRUD Endpoints ====================

@app.get("/api/audit_log")
def api_list_audit_log() -> Any:
    return jsonify(*audit_controller.handle_list_audit_log(request))


def main() -> None:
    db_path = os.getenv("DLG_SQLITE_PATH", "dlg_analysis.db")

    logger.info("Application initialized with database: %s", db_path)

    global crawler_controller, lsp_master_controller, audit_controller

    crawler_controller = DlgCrawlerController()
    lsp_master_controller = LSPMasterController()
    audit_controller = AuditLogController()

    # Setup cron job scheduler if enabled
    if os.getenv("DLG_CRON_ENABLED", "0") in {"1", "true", "True"}:
        if not APSCHEDULER_AVAILABLE:
            raise RuntimeError("APScheduler not installed; add it to requirements.txt")

        # Only start scheduler once (avoid Flask reloader double-start)
        if not settings.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            cron_expr = os.getenv("DLG_CRON", "0 * * * *")  # Default: top of every hour
            timezone = os.getenv("DLG_CRON_TZ", "UTC")

            scheduler = BackgroundScheduler(timezone=timezone)
            scheduler.add_job(
                crawler_controller.run_scrape(),
                CronTrigger.from_crontab(cron_expr)
            )
            scheduler.start()

            logger.info("Cron scheduler started: %s (%s)", cron_expr, timezone)

    # Run Flask server
    logger.info("Starting Flask server on %s:%d", settings.host, settings.port)
    app.run(host=settings.host, port=settings.port, debug=settings.debug)


if __name__ == "__main__":
    main()
