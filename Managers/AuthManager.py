"""
AuditLogService with DB support for audit logs.
"""
from werkzeug.security import generate_password_hash, check_password_hash
from typing import Optional, Any, Dict

from sqlalchemy import desc, asc, or_
from sqlalchemy.exc import SQLAlchemyError
from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.DatabaseModels.master_models import Users
from utils.logger_config import logger_method


class AuthManager:
    """Manager for user authentication and user CRUD operations."""

    def __init__(self, user_claims: Optional[Dict[str, Any]] = None):
        self.conn_factory = ConnectionFactory()
        self.logger = logger_method(__name__)

    def find_user(self, username: str, role: str) -> Optional[Users]:

        session = self.conn_factory.get_session()
        try:
            return session.query(Users).filter_by(username=username, role=role).one_or_none()
        except Exception:
            session.rollback()
            self.logger.critical(f"Error querying user username={username} role={role}")
            raise
        finally:
            session.close()

    def find_user_by_username(self, username: str) -> Optional[Users]:
        session = self.conn_factory.get_session()
        try:
            return session.query(Users).filter_by(username=username).one_or_none()
        except Exception:
            session.rollback()
            self.logger.critical(f"Error querying user by username={username}")
            raise
        finally:
            session.close()

    @staticmethod
    def hash_password(plain_password: str) -> str:
        """Hash a plain text password."""
        hashed = generate_password_hash(plain_password, method='pbkdf2:sha256')
        return hashed

    @staticmethod
    def verify_password(user_password: str, hashed_password: str) -> bool:
        """Verify a user password against a hashed password from DB."""
        return check_password_hash(hashed_password, user_password)


