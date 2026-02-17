"""
SQLAlchemy ORM models for DLG analysis master tables.
"""
from sqlalchemy import Column, String, Boolean, Float, Enum as SAEnum, Integer, ForeignKey, TIMESTAMP, JSON
from sqlalchemy.orm import declarative_base
from typing import Optional
from dataclasses import dataclass
from utils.constants import AuditAction, CrawlStatus, LSPType

Base = declarative_base()


@dataclass
class LspMasterIp:
    lsp_name: str
    lsp_home_url: str
    brand_name: str
    lsp_type: str


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
    brand_name = Column(String, nullable=False)
    lsp_type = Column(String, nullable=True)
    home_url = Column(String, nullable=False)
    active = Column(Boolean, default=True)
    dlg_url = Column(String)
    parse_hint = Column(String, default="auto")
    fetch_hint = Column(String, default="auto")
    rules_json = Column(JSON, default=dict)
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
    action_taken = Column(String, nullable=False)
    log_timestamp = Column(TIMESTAMP(timezone=True))


class Users(Base):
    __tablename__ = "dlg_users"
    __table_args__ = {'schema': 'dlg'}
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, primary_key=True, nullable=False)
    role = Column(String, primary_key=True, nullable=False)
    firstname = Column(String, nullable=False)
    lastname = Column(String)
    password = Column(String)
    active = Column(Boolean, default=True)
    reset_password = Column(Boolean, default=True)
    create_date = Column(TIMESTAMP(timezone=True))
    modify_date = Column(TIMESTAMP(timezone=True))
    last_login = Column(TIMESTAMP(timezone=True))


@dataclass
class UserInput:
    username: str
    role: str
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    reset_password: Optional[bool] = None
    active: Optional[bool] = None


@dataclass
class UserUpdate:
    username: str
    id: int
    role: Optional[str] = None
    password: Optional[str] = None
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    reset_password: Optional[bool] = None
    active: Optional[bool] = None
