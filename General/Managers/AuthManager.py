"""
AuditLogService with DB support for audit logs.
"""
import datetime as dt
import json
from typing import Optional, Any, Dict

from sqlalchemy import desc, asc, or_
from sqlalchemy.exc import SQLAlchemyError
from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.DatabaseModels.master_models import Users, Base, UserInput
from utils.logger_config import logger_method


class AuthManager:
    """Manager for user authentication and user CRUD operations."""

    def __init__(self, user_claims: Optional[Dict[str, Any]] = None):
        self.conn_factory = ConnectionFactory()

    def find_user(self, username: str, role: str) -> Optional[Users]:

        session = self.conn_factory.get_session()
        try:
            return session.query(Users).filter_by(username=username, role=role).one_or_none()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def find_user_by_username(self, username: str) -> Optional[Users]:
        session = self.conn_factory.get_session()
        try:
            return session.query(Users).filter_by(username=username).one_or_none()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()