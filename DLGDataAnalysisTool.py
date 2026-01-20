"""Flask entrypoint that exposes controller-based scrape operations."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict

from dotenv import load_dotenv
from flask import Flask, jsonify, request

from General.Controllers.DlgCrawlerController import DlgCrawlerController
from General.Managers.LspMasterManagerDB import LspMasterManagerDB
from General.Managers.DlgCrawlerConfigManagerDB import DlgCrawlerConfigManagerDB
from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.SQLAlchemy.DatabaseModels.orm_models import Base

# Load environment variables from .env file
load_dotenv()


@dataclass(slots=True)
class AppSettings:
    """Holds default paths and HTTP server knobs."""

    master_csv: str = os.getenv("DLG_MASTER_CSV", "data\\lsp_sources_latest.csv")
    raw_csv: str = os.getenv("DLG_RAW_CSV", "data\\dlg_raw_latest_v39.csv")
    host: str = os.getenv("DLG_FLASK_HOST", "0.0.0.0")
    port: int = int(os.getenv("DLG_FLASK_PORT", "5000"))
    debug: bool = os.getenv("DLG_FLASK_DEBUG", "0") in {"1", "true", "True"}


settings = AppSettings()
controller = DlgCrawlerController()
app = Flask(__name__)

# ensure DB tables exist
conn = ConnectionFactory(os.getenv("DLG_SQLITE_PATH", "dlg_analysis.db"))
conn.create_all_tables(base=Base)

# DB managers (API-only population)
lsp_db = LspMasterManagerDB(os.getenv("DLG_SQLITE_PATH", "dlg_analysis.db"))
config_db = DlgCrawlerConfigManagerDB(os.getenv("DLG_SQLITE_PATH", "dlg_analysis.db"))


@app.get("/healthz")
def healthcheck() -> Any:
    return jsonify({
        "status": "ok",
        "default_master_csv": settings.master_csv,
        "default_raw_csv": settings.raw_csv,
    })


@app.post("/scrape")
def trigger_scrape() -> Any:
    payload: Dict[str, Any] = request.get_json(silent=True) or {}
    master_csv = payload.get("master_csv") or settings.master_csv
    raw_csv = payload.get("raw_csv") or settings.raw_csv
    limit = payload.get("limit")

    try:
        controller.run_scrape(master_csv, raw_csv, limit)
    except Exception as exc:  # pragma: no cover - exposed to caller
        return (
            jsonify({
                "status": "error",
                "message": str(exc),
            }),
            500,
        )

    return jsonify({
        "status": "ok",
        "master_csv": master_csv,
        "raw_csv": raw_csv,
        "limit": limit,
    })


@app.post("/api/lsp_master")
def api_upsert_lsp_master() -> Any:
    """Accepts a JSON object or list of LSPs and upserts into the DB.

    Expected JSON object fields: `lsp_name`, `disclosure_url`, `is_active`,
    optionally `lsp_id` and `home_url`.
    """
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"status": "error", "message": "empty payload"}), 400

    items = payload if isinstance(payload, list) else [payload]
    from DatabaseOperation.SQLAlchemy.DatabaseModels import LspMaster as LspMasterDC

    rows = []
    for it in items:
        lm = LspMasterDC(
            lsp_name=it.get("lsp_name") or it.get("name"),
            disclosure_url=it.get("disclosure_url") or it.get("home_url") or "",
            is_active=bool(it.get("is_active", True)),
            fetch_hint=it.get("fetch_hint", "auto"),
            parse_hint=it.get("parse_hint", "auto"),
            rules_json=it.get("rules_json"),
            lsp_id=it.get("lsp_id") or it.get("id") or None,
            home_url=it.get("home_url") or None,
        )
        rows.append(lm)

    try:
        count = lsp_db.bulk_upsert(rows)
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

    return jsonify({"status": "ok", "upserted": count})


@app.post("/api/dlg_crawler_config")
def api_upsert_dlg_config() -> Any:
    """Accepts a JSON object or list of configs and upserts into DB.

    Expected fields per item: `lsp_id`, `dlg_url`, `is_active`, `fetch_hint`, `parse_hint`, `rules_json`.
    """
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"status": "error", "message": "empty payload"}), 400

    items = payload if isinstance(payload, list) else [payload]
    from DatabaseOperation.SQLAlchemy.DatabaseModels import DlgCrawlerConfig as DlgCrawlerConfigDC

    rows = []
    for it in items:
        lsp_id = it.get("lsp_id") or it.get("id")
        if not lsp_id:
            return jsonify({"status": "error", "message": "lsp_id required"}), 400
        dlg_url = it.get("dlg_url") or it.get("disclosure_url") or it.get("dlg_url") or ""
        cfg = DlgCrawlerConfigDC(
            fetch_hint=it.get("fetch_hint", "auto"),
            parse_hint=it.get("parse_hint", "auto"),
            pre_click_js=it.get("pre_click_js"),
            rules_json=it.get("rules_json"),
        )
        rows.append((lsp_id, cfg, dlg_url))

    try:
        count = config_db.bulk_upsert(rows)
    except Exception as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500

    return jsonify({"status": "ok", "upserted": count})


@app.get("/api/lsp_master")
def api_list_lsp_master() -> Any:
    """Return up to 1000 rows from lsp_master for verification."""
    from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
    from DatabaseOperation.SQLAlchemy.DatabaseModels.orm_models import LspMasterORM
    db_path = os.getenv("DLG_SQLITE_PATH", "dlg_analysis.db")
    cf = ConnectionFactory(db_path)
    session = cf.get_session()
    try:
        rows = session.query(LspMasterORM).limit(1000).all()
        results = [ {"id": r.id, "legacy_id": getattr(r, 'legacy_id', None), "name": r.name, "home_url": r.home_url, "active": r.active} for r in rows ]
    finally:
        session.close()
    return jsonify({"status": "ok", "count": len(results), "rows": results})


@app.get("/api/dlg_crawler_config")
def api_list_dlg_crawler_config() -> Any:
    """Return up to 1000 rows from dlg_crawler_config for verification."""
    from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
    from DatabaseOperation.SQLAlchemy.DatabaseModels.orm_models import DlgCrawlerConfigORM
    db_path = os.getenv("DLG_SQLITE_PATH", "dlg_analysis.db")
    cf = ConnectionFactory(db_path)
    session = cf.get_session()
    try:
        rows = session.query(DlgCrawlerConfigORM).limit(1000).all()
        results = [ {"lsp_id": r.lsp_id, "dlg_url": r.dlg_url, "is_active": r.is_active, "fetch_hint": r.fetch_hint, "parse_hint": r.parse_hint, "rules_json": r.rules_json} for r in rows ]
    finally:
        session.close()
    return jsonify({"status": "ok", "count": len(results), "rows": results})


@app.delete("/api/lsp_master/<lsp_id>")
def api_delete_lsp_master(lsp_id: str) -> Any:
    """Delete an LSP by `lsp_id` and its config if present."""
    from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
    from DatabaseOperation.SQLAlchemy.DatabaseModels.orm_models import LspMasterORM, DlgCrawlerConfigORM
    db_path = os.getenv("DLG_SQLITE_PATH", "dlg_analysis.db")
    cf = ConnectionFactory(db_path)
    session = cf.get_session()
    try:
        # allow either numeric id or legacy string id in the route
        try:
            int_id = int(lsp_id)
            lm = session.query(LspMasterORM).filter_by(id=int_id).one_or_none()
        except Exception:
            lm = session.query(LspMasterORM).filter_by(legacy_id=lsp_id).one_or_none()
        if not lm:
            return jsonify({"status": "error", "message": "not found"}), 404
        # delete config if exists
        cfg = session.query(DlgCrawlerConfigORM).filter_by(lsp_id=lm.id).one_or_none()
        if cfg:
            session.delete(cfg)
        session.delete(lm)
        session.commit()
        return jsonify({"status": "ok", "deleted": lsp_id})
    except Exception as exc:
        session.rollback()
        return jsonify({"status": "error", "message": str(exc)}), 500
    finally:
        session.close()


@app.delete("/api/dlg_crawler_config/<lsp_id>")
def api_delete_dlg_crawler_config(lsp_id: str) -> Any:
    """Delete only the crawler config for `lsp_id`."""
    from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
    from DatabaseOperation.SQLAlchemy.DatabaseModels.orm_models import DlgCrawlerConfigORM, LspMasterORM
    db_path = os.getenv("DLG_SQLITE_PATH", "dlg_analysis.db")
    cf = ConnectionFactory(db_path)
    session = cf.get_session()
    try:
        # accept numeric id or legacy string id
        try:
            int_id = int(lsp_id)
            cfg = session.query(DlgCrawlerConfigORM).filter_by(lsp_id=int_id).one_or_none()
        except Exception:
            lm = session.query(LspMasterORM).filter_by(legacy_id=lsp_id).one_or_none()
            if not lm:
                return jsonify({"status": "error", "message": "not found"}), 404
            cfg = session.query(DlgCrawlerConfigORM).filter_by(lsp_id=lm.id).one_or_none()
        if not cfg:
            return jsonify({"status": "error", "message": "not found"}), 404
        session.delete(cfg)
        session.commit()
        return jsonify({"status": "ok", "deleted": lsp_id})
    except Exception as exc:
        session.rollback()
        return jsonify({"status": "error", "message": str(exc)}), 500
    finally:
        session.close()


def main() -> None:
    app.run(host=settings.host, port=settings.port, debug=settings.debug)


if __name__ == "__main__":
    main()
