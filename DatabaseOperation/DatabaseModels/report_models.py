"""
SQLAlchemy ORM models for DLG analysis reports tables.
"""
from sqlalchemy import Column, String, Boolean, Float, Integer, ForeignKey, TIMESTAMP, JSON
from sqlalchemy.orm import declarative_base
import os
from enum import Enum
from dataclasses import dataclass

Base = declarative_base()


class LspSummary(Base):
    __tablename__ = "lsp_summary"
    __table_args__ = {'schema': 'reports'}
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
