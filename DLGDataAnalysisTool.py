"""Flask entrypoint for DLG scraping and analysis REST API.

Clean architecture entrypoint:
- Application initialization and configuration
- Flask route definitions (thin wrappers)
- All business logic delegated to controllers
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict

from dotenv import load_dotenv
import logging
from flask import Flask, jsonify, request
from utils.db_activity_logger import setup_db_activity_logger
from utils.logger_config import setup_logging

from General.Controllers.DlgCrawlerController import DlgCrawlerController
from General.Controllers.ApiController import ApiController
from General.Controllers.ScrapingController import ScrapingController
from DatabaseOperation.SQLAlchemy.DatabaseManager import get_db_manager

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_AVAILABLE = True
except Exception:
    APSCHEDULER_AVAILABLE = False

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppSettings:
    """HTTP server configuration."""

    host: str = os.getenv("DLG_FLASK_HOST", "0.0.0.0")
    port: int = int(os.getenv("DLG_FLASK_PORT", "5000"))
    debug: bool = os.getenv("DLG_FLASK_DEBUG", "0") in {"1", "true", "True"}


# Application configuration
settings = AppSettings()
app = Flask(__name__)

# Controllers (initialized in main)
crawler_controller = None
api_controller = None
scraping_controller = None


# ==================== Health & Utility Endpoints ====================

@app.get("/healthz")
def healthcheck() -> Any:
    return jsonify({"status": "ok", "message": "OK"})


@app.post("/scrape")
def trigger_scrape() -> Any:
    return jsonify(*api_controller.handle_trigger_scrape(request, crawler_controller))


# ==================== LspMaster CRUD Endpoints ====================

@app.post("/api/lsp_master")
def api_upsert_lsp_master() -> Any:
    return jsonify(*api_controller.handle_upsert_lsp_master(request))


@app.get("/api/lsp_master")
def api_list_lsp_master() -> Any:
    return jsonify(*api_controller.handle_list_lsp_master(request))


@app.get("/api/lsp_master/<int:id>")
def api_get_lsp_master(id: int) -> Any:
    return jsonify(*api_controller.handle_get_lsp_master(id))


@app.put("/api/lsp_master/<int:id>")
def api_update_lsp_master(id: int) -> Any:
    return jsonify(*api_controller.handle_update_lsp_master(id, request))


@app.delete("/api/lsp_master/<lsp_id>")
def api_delete_lsp_master(lsp_id: str) -> Any:
    return jsonify(*api_controller.handle_delete_lsp_master(lsp_id))


# ==================== DlgCrawlerConfig CRUD Endpoints ====================

@app.post("/api/dlg_crawler_config")
def api_upsert_dlg_config() -> Any:
    return jsonify(*api_controller.handle_upsert_dlg_config(request))


@app.get("/api/dlg_crawler_config")
def api_list_dlg_crawler_config() -> Any:
    return jsonify(*api_controller.handle_list_dlg_config(request))


@app.get("/api/dlg_crawler_config/<int:lsp_id>")
def api_get_dlg_crawler_config(lsp_id: int) -> Any:
    return jsonify(*api_controller.handle_get_dlg_config(lsp_id))


@app.put("/api/dlg_crawler_config/<int:lsp_id>")
def api_update_dlg_crawler_config(lsp_id: int) -> Any:
    return jsonify(*api_controller.handle_update_dlg_config(lsp_id, request))


@app.delete("/api/dlg_crawler_config/<lsp_id>")
def api_delete_dlg_crawler_config(lsp_id: str) -> Any:
    return jsonify(*api_controller.handle_delete_dlg_config(lsp_id))


# ==================== DlgRaw CRUD Endpoints ====================

@app.post("/api/dlg_raw")
def api_create_dlg_raw() -> Any:
    return jsonify(*api_controller.handle_create_dlg_raw(request))


@app.get("/api/dlg_raw")
def api_list_dlg_raw() -> Any:
    return jsonify(*api_controller.handle_list_dlg_raw(request))


# ==================== AuditLog CRUD Endpoints ====================

@app.post("/api/audit_log")
def api_create_audit_log() -> Any:
    return jsonify(*api_controller.handle_create_audit_log(request))


@app.get("/api/audit_log")
def api_list_audit_log() -> Any:
    return jsonify(*api_controller.handle_list_audit_log(request))


@app.get("/api/audit_log/<int:id>")
def api_get_audit_log(id: int) -> Any:
    return jsonify(*api_controller.handle_get_audit_log(id))


@app.delete("/api/audit_log/<int:id>")
def api_delete_audit_log(id: int) -> Any:
    return jsonify(*api_controller.handle_delete_audit_log(id))


def main() -> None:
    """Application entrypoint - initialize and run Flask server."""
    # Configure logging
    setup_logging(level=os.getenv("DLG_LOG_LEVEL", "INFO"))
    setup_db_activity_logger()

    # Initialize singleton controllers
    global crawler_controller, api_controller, scraping_controller
    
    db_path = os.getenv("DLG_SQLITE_PATH", "dlg_analysis.db")
    _ = get_db_manager(db_path)  # Initialize DB singleton
    
    crawler_controller = DlgCrawlerController()
    api_controller = ApiController()
    scraping_controller = ScrapingController()
    
    logger.info("Application initialized with database: %s", db_path)

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
                scraping_controller.run_cron_scrape,
                CronTrigger.from_crontab(cron_expr)
            )
            scheduler.start()
            
            logger.info("Cron scheduler started: %s (%s)", cron_expr, timezone)

    # Run Flask server
    logger.info("Starting Flask server on %s:%d", settings.host, settings.port)
    app.run(host=settings.host, port=settings.port, debug=settings.debug)


if __name__ == "__main__":
    main()
