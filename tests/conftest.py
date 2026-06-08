"""Shared pytest setup: keeps tests off real AWS secrets and real Postgres."""
import os

os.environ["LOCAL_DEV"] = "1"
os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ.setdefault("DLG_SQLITE_PATH", ":memory:")

for _key in ("database_username", "database_password", "database_host", "database_port", "database_name"):
    os.environ.pop(_key, None)
