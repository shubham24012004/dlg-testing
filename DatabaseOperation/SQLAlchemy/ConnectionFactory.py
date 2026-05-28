"""
ConnectionFactory for SQLite using SQLAlchemy ORM.
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()


POSTGRES_ENV_VARS = (
    "database_username",
    "database_password",
    "database_host",
    "database_port",
    "database_name",
)

class ConnectionFactory:
    """Provides SQLAlchemy engine and session for SQLite."""

    def __init__(self):
        postgres_config = {key: os.getenv(key) for key in POSTGRES_ENV_VARS}
        present_keys = [key for key, value in postgres_config.items() if value]

        if present_keys:
            missing_keys = [key for key, value in postgres_config.items() if not value]
            if missing_keys:
                missing = ", ".join(missing_keys)
                raise RuntimeError(
                    f"Incomplete PostgreSQL configuration. Missing environment variables: {missing}"
                )

            db_url = (
                f"postgresql://{postgres_config['database_username']}:{postgres_config['database_password']}"
                f"@{postgres_config['database_host']}:{postgres_config['database_port']}"
                f"/{postgres_config['database_name']}"
            )
            # Use PostgreSQL or other database
            self.engine = create_engine(db_url, echo=False, future=True)
        else:
            db_path = os.getenv("DLG_SQLITE_PATH", "dlg_analysis.db")
            self.engine = create_engine(f"sqlite:///{db_path}", echo=False, future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

    def get_session(self):
        return self.SessionLocal()

    def create_all_tables(self, base=Base):
        db_url = str(self.engine.url)
        if db_url.startswith("postgresql"):
            from sqlalchemy import text
            schemas = {
                tbl.schema for tbl in base.metadata.tables.values() if tbl.schema
            }
            with self.engine.begin() as conn:
                for schema in schemas:
                    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema}"))
        base.metadata.create_all(self.engine)
