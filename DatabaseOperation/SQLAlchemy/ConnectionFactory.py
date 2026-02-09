"""
ConnectionFactory for SQLite using SQLAlchemy ORM.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os

Base = declarative_base()
load_dotenv()

class ConnectionFactory:
    """Provides SQLAlchemy engine and session for SQLite."""

    def __init__(self):
        db_url = f'postgresql://{os.getenv("database_username")}:{os.getenv("database_password")}@{os.getenv("database_host")}:{os.getenv("database_port")}/{os.getenv("database_name")}'
        if db_url:
            # Use PostgreSQL or other database
            self.engine = create_engine(db_url, echo=False, future=True)
        else:
            db_path = os.getenv("DLG_SQLITE_PATH", "dlg_analysis.db")
            self.engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

    def get_session(self):
        return self.SessionLocal()

    def create_all_tables(self, base=Base):
        base.metadata.create_all(self.engine)
