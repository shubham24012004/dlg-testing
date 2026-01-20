"""
ConnectionFactory for SQLite using SQLAlchemy ORM.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

Base = declarative_base()

class ConnectionFactory:
    """Provides SQLAlchemy engine and session for SQLite."""
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.getenv("DLG_SQLITE_PATH", "dlg_analysis.db")
        self.engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

    def get_session(self):
        return self.SessionLocal()

    def create_all_tables(self, base=Base):
        base.metadata.create_all(self.engine)
