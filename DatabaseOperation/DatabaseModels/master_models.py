"""
SQLAlchemy ORM models for DLG analysis master tables.
"""
from sqlalchemy import Column, String, Boolean, Float, Enum as SAEnum, Integer, ForeignKey, TIMESTAMP, JSON
from sqlalchemy.orm import declarative_base
import os
from enum import Enum
from dataclasses import dataclass

Base = declarative_base()


class AuditAction(Enum):
    INSERT_LSP = os.getenv("AUDIT_ACTION_INSERT_LSP", "INSERT_LSP")
    UPDATE_LSP = os.getenv("AUDIT_ACTION_UPDATE_LSP", "UPDATE_LSP")
    DELETE_LSP = os.getenv("AUDIT_ACTION_DELETE_LSP", "DELETE_LSP")
    URL_FINDER = os.getenv("AUDIT_ACTION_URL_FINDER", "URL_FINDER")
    LSP_SUMMARY = os.getenv("AUDIT_ACTION_LSP_SUMMARY", "LSP_SUMMARY")
    CRAWL = os.getenv("AUDIT_ACTION_CRAWL", "CRAWL")


class CrawlStatus(Enum):
    COMPLETED = os.getenv("CRAWL_STATUS_COMPLETED", "Completed") # All data fetched successfully
    PARTIAL = os.getenv("CRAWL_STATUS_PARTIAL", "Partial") # Some data missing Amount/Portfolio/As on date
    ERROR = os.getenv("CRAWL_STATUS_ERROR", "Error") # Error during fetch/parse
    MISSING = os.getenv("CRAWL_STATUS_MISSING", "Missing") # DLG URL MISSING
    STALE = os.getenv("CRAWL_STATUS_STALE", "Stale") # as on date MISSING
    NO_DATA = os.getenv("CRAWL_STATUS_NO_DATA", "NoData") # PAGE AVAILABLE DATA NOT AVAILABLE


@dataclass
class LspMasterIp:
    lsp_name: str
    lsp_home_url: str


@dataclass
class FetchResult:
    url: str
    status_code: int
    content_type: str
    body: bytes
    fetch_mode_used: str  # requests|playwright


class LspMaster(Base):
    __tablename__ = "lsp_master"
    __table_args__ = {'schema': 'dlg'}
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    home_url = Column(String, nullable=False)
    active = Column(Boolean, default=True)
    dlg_url = Column(String)
    parse_hint = Column(String, default="auto")
    fetch_hint = Column(String, default="auto")
    rules_json = Column(JSON, default='{}')
    last_crawl_date = Column(TIMESTAMP(timezone=True))


class DlgRaw(Base):
    __tablename__ = "dlg_raw"
    __table_args__ = {'schema': 'dlg'}
    id = Column(Integer, primary_key=True, autoincrement=True)
    lsp_id = Column(Integer, primary_key=True)
    lsp_name = Column(String, primary_key=True)
    lender = Column(String, nullable=True)
    portfolio = Column(String, nullable=True)
    amount = Column(Float)
    as_on_timestamp = Column(TIMESTAMP(timezone=True), nullable=True)
    scrape_timestamp = Column(TIMESTAMP(timezone=True))
    complete = Column(String)


class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = {'schema': 'dlg'}
    id = Column(Integer, primary_key=True, autoincrement=True)
    lsp_id = Column(Integer, nullable=True)
    auto_manual = Column(String)
    user_id = Column(String)
    payload = Column(JSON)
    action_taken = Column(SAEnum(AuditAction), nullable=False)
    log_timestamp = Column(TIMESTAMP(timezone=True))
