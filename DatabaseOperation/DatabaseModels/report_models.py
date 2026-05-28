"""
SQLAlchemy ORM models for DLG analysis reports tables.
"""
import os
from sqlalchemy import Column, String, Boolean, Float, Integer, ForeignKey, TIMESTAMP, JSON, UniqueConstraint
from sqlalchemy.orm import declarative_base
from enum import Enum
from dataclasses import dataclass

POSTGRES_ENV_VARS = (
    "database_username",
    "database_password",
    "database_host",
    "database_port",
    "database_name",
)
USE_POSTGRES = all(os.getenv(key) for key in POSTGRES_ENV_VARS)
REPORTS_SCHEMA = "reports" if USE_POSTGRES else None

Base = declarative_base()


class LspSummary(Base):
    __tablename__ = "lsp_summary"
    __table_args__ = (
        UniqueConstraint('lsp_id', 'scrape_year', 'scrape_month', name='uq_lsp_summary_lsp_year_month'),
        {'schema': REPORTS_SCHEMA} if REPORTS_SCHEMA else {},
    )
    id = Column(Integer, primary_key=True, autoincrement=True)
    lsp_id = Column(Integer, nullable=False)
    name = Column(String, nullable=False)
    total_lenders = Column(Integer, nullable=True)
    total_portfolios = Column(Integer, nullable=True)
    total_amount = Column(Float, nullable=True)
    dlg_url = Column(String, nullable=True)
    as_on_year = Column(Integer, nullable=True)
    as_on_month = Column(Integer, nullable=True)
    scrape_year = Column(Integer, nullable=True)
    scrape_month = Column(Integer, nullable=True)
    status = Column(String, nullable=True)
    last_crawl_date = Column(TIMESTAMP(timezone=True))
