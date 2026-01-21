"""DB activity logger: logs inserts/updates/deletes and session commits to a file.

This attaches SQLAlchemy mapper and session event listeners and writes human
readable JSON-ish entries to `logs/db_activity.log`.
"""
from __future__ import annotations

import json
import logging
import os
from logging.handlers import RotatingFileHandler

from sqlalchemy import event
from sqlalchemy.inspection import inspect as sa_inspect
from sqlalchemy.orm import Session as SessionClass

# import the declarative base so we can iterate mappers
from DatabaseOperation.SQLAlchemy.DatabaseModels.orm_models import Base


LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
LOG_FILE = os.path.abspath(os.path.join(LOG_DIR, "db_activity.log"))


def _ensure_log_dir() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)


def get_logger() -> logging.Logger:
    logger = logging.getLogger("dlg.db")
    if not logger.handlers:
        _ensure_log_dir()
        handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
        fmt = "%(asctime)s %(levelname)s %(message)s"
        handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def _format_pk(target) -> str:
    try:
        insp = sa_inspect(target)
        if insp.identity:
            return str(insp.identity)
    except Exception:
        pass
    return "unknown"


def _serialize_obj(target) -> dict:
    out = {}
    for k, v in vars(target).items():
        if k.startswith("_sa_"):
            continue
        try:
            # ensure JSON serializable
            json.dumps(v)
            out[k] = v
        except Exception:
            out[k] = repr(v)
    return out


def setup_db_activity_logger() -> None:
    """Configure file logger and register SQLAlchemy event listeners.

    Call early in application startup (before heavy DB activity).
    """
    logger = get_logger()

    def _after_insert(mapper, connection, target):
        try:
            name = getattr(mapper.local_table, "name", str(mapper))
        except Exception:
            name = getattr(target, "__tablename__", "unknown")
        logger.info("DB INSERT %s pk=%s data=%s", name, _format_pk(target), json.dumps(_serialize_obj(target), default=str))

    def _after_update(mapper, connection, target):
        try:
            name = getattr(mapper.local_table, "name", str(mapper))
        except Exception:
            name = getattr(target, "__tablename__", "unknown")
        insp = sa_inspect(target)
        changes = {}
        for attr in insp.attrs:
            try:
                if attr.history.has_changes():
                    changes[attr.key] = attr.value
            except Exception:
                continue
        logger.info("DB UPDATE %s pk=%s changes=%s", name, _format_pk(target), json.dumps(changes, default=str))

    def _after_delete(mapper, connection, target):
        try:
            name = getattr(mapper.local_table, "name", str(mapper))
        except Exception:
            name = getattr(target, "__tablename__", "unknown")
        logger.info("DB DELETE %s pk=%s data=%s", name, _format_pk(target), json.dumps(_serialize_obj(target), default=str))

    # register mapper-level listeners for existing mappers
    for m in list(Base.registry.mappers):
        try:
            event.listen(m, "after_insert", _after_insert)
            event.listen(m, "after_update", _after_update)
            event.listen(m, "after_delete", _after_delete)
        except Exception:
            # continue attaching to others even if one fails
            logger.exception("failed attaching mapper listeners for %s", m)

    # session-level events
    def _after_commit(session):
        logger.info("DB COMMIT session_id=%s", id(session))

    def _after_rollback(session):
        logger.warning("DB ROLLBACK session_id=%s", id(session))

    try:
        event.listen(SessionClass, "after_commit", _after_commit)
        event.listen(SessionClass, "after_rollback", _after_rollback)
    except Exception:
        logger.exception("failed attaching session listeners")


__all__ = ["setup_db_activity_logger", "get_logger"]
