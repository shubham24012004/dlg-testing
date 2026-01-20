"""
SQLAlchemy ORM models for DLG analysis tables.
"""
from sqlalchemy import Column, String, Boolean, Float, DateTime, Enum as SAEnum, Text, Integer, ForeignKey
from sqlalchemy.orm import declarative_base
import datetime as dt
import os
from enum import Enum

Base = declarative_base()

class AuditAction(Enum):
    INSERT_LSP = os.getenv("AUDIT_ACTION_INSERT_LSP", "INSERT_LSP")
    UPDATE_LSP = os.getenv("AUDIT_ACTION_UPDATE_LSP", "UPDATE_LSP")
    DELETE_LSP = os.getenv("AUDIT_ACTION_DELETE_LSP", "DELETE_LSP")
    URL_FINDER = os.getenv("AUDIT_ACTION_URL_FINDER", "URL_FINDER")
    CRAWL = os.getenv("AUDIT_ACTION_CRAWL", "CRAWL")

class LspMasterORM(Base):
    __tablename__ = "lsp_master"
    id = Column(Integer, primary_key=True, autoincrement=True)
    legacy_id = Column(String, unique=True, nullable=True)
    name = Column(String, nullable=False)
    home_url = Column(String)
    active = Column(Boolean, default=True)

class DlgCrawlerConfigORM(Base):
    __tablename__ = "dlg_crawler_config"
    lsp_id = Column(Integer, ForeignKey("lsp_master.id"), primary_key=True)
    dlg_url = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    parse_hint = Column(String, default="auto")
    fetch_hint = Column(String, default="auto")
    rules_json = Column(Text)
    last_crawl_date = Column(DateTime)

class DlgRawORM(Base):
    __tablename__ = "dlg_raw"
    lsp_id = Column(Integer, primary_key=True)
    lsp_name = Column(String, primary_key=True)
    lender = Column(String, primary_key=True)
    portfolio = Column(String, primary_key=True)
    amount = Column(Float)
    as_on_timestamp = Column(DateTime, primary_key=True)
    scrape_timestamp = Column(DateTime, primary_key=True)
    complete = Column(String)

class AuditLogORM(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    lsp_id = Column(Integer, nullable=True)
    legacy_lsp_id = Column(String, nullable=True)
    auto_manual = Column(String)
    user_id = Column(String)
    payload = Column(Text)
    action_taken = Column(SAEnum(AuditAction), nullable=False)
