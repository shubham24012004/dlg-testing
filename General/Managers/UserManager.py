"""
AuditLogService with DB support for audit logs.
"""
import datetime as dt
import json
from typing import Optional, Any, Dict

from sqlalchemy import desc, asc, or_
from sqlalchemy.exc import SQLAlchemyError
from DatabaseOperation.SQLAlchemy.ConnectionFactory import ConnectionFactory
from DatabaseOperation.DatabaseModels.master_models import Users, Base, UserInput, UserUpdate
from utils.logger_config import logger_method


class UserManager:
    """Manager for user authentication and user CRUD operations."""

    def __init__(self, user_claims: Optional[Dict[str, Any]] = None):
        self.conn_factory = ConnectionFactory()
        self.conn_factory.create_all_tables(base=Base)
        self.user_claims = user_claims
        self.logger = logger_method(__name__)

    def _get_user_info(self) -> str:
        if not self.user_claims:
            return "[User: system, Role: unknown]"
        username = self.user_claims.get('username', 'unknown')
        user_role = self.user_claims.get('role', 'unknown')
        return f"[User: {username}, Role: {user_role}]"

    def create(self, user_details: UserInput) -> Optional[Dict[str, Any]]:
        """Create a new user record.

        Args:
            user_details: dict containing at least username, password, firstname, role

        Returns:
            dict with created user summary or None on validation failure.
        """
        session = self.conn_factory.get_session()
        try:
            # ensure user does not already exist
            existing = session.query(Users).filter_by(username=user_details.username).filter_by(role=user_details.role).one_or_none()
            if existing:
                self.logger.error(f"{self._get_user_info()} User already exists")
                return None

            now = dt.datetime.utcnow()
            user = Users(
                username=user_details.username,
                firstname=user_details.firstname,
                lastname=user_details.lastname,
                role=user_details.role,
                password=user_details.password,
                active=True,
                reset_password=True,
                create_date=now,
                modify_date=now,
            )
            session.add(user)
            session.commit()
            self.logger.info(f"{self._get_user_info()} {user_details.username} User Created Successfully")
            return {"id": user.id, "username": user_details.username, "role": user_details.role}
        except SQLAlchemyError:
            session.rollback()
            raise
        finally:
            session.close()

    def update(self, user_id: int, user_details: UserUpdate) -> Optional[Dict[str, Any]]:
        """Update an existing user record.

        Args:
            user_id: user id of the user to update
            user_details: UserInput object with fields to update (only non-None fields will be updated)

        Returns:
            dict with updated user summary or None if user not found.
        """
        session = self.conn_factory.get_session()
        try:
            existing_user = session.query(Users).filter_by(id=user_id).one_or_none()

            if not existing_user:
                self.logger.error(f"{self._get_user_info()} User not found")
                return None

            if user_details.firstname is not None:
                existing_user.firstname = user_details.firstname
            if user_details.role is not None:
                existing_user.role = user_details.role
            if user_details.lastname is not None:
                existing_user.lastname = user_details.lastname
            if user_details.password is not None:
                existing_user.password = user_details.password
            if user_details.reset_password is not None:
                existing_user.reset_password = user_details.reset_password
            if user_details.active is not None:
                existing_user.active = user_details.active

            existing_user.modify_date = dt.datetime.utcnow()

            session.add(existing_user)
            session.commit()
            self.logger.info(f"{self._get_user_info()} {user_details.username} User Updated Successfully")
            return {
                "id": existing_user.id,
                "username": existing_user.username,
                "firstname": existing_user.firstname,
                "lastname": existing_user.lastname,
                "active": existing_user.active,
                "reset_password": existing_user.reset_password,
            }
        except SQLAlchemyError:
            session.rollback()
            raise
        finally:
            session.close()

    def list_users(
            self, active_only: bool = False, page_size: int = 10, page: int = 1, username: str = None, role: str = None
    ) -> tuple[list[dict[Any, Any] | dict[str, Any] | dict[str, str]], Any, Any]:
        """List user records.

        Args:
            :param role: role to search by
            :param username: search string for username or firstname
            :param active_only: If True, only return active users
            :param page: page number
            :param page_size: page size

        Returns:
            List of dict of filtered users
            count
        """

        session = self.conn_factory.get_session()
        try:
            query = session.query(Users).order_by(asc(Users.id))
            query = query.filter_by(active=active_only)
            if role:
                query = query.filter_by(role=role)
            if username:
                search_name = f'%{username}%'
                query = query.filter(
                    or_(Users.username.like(search_name), Users.firstname.like(search_name))
                )
            # capture total count before pagination
            total_count = query.count()
            if page:
                query = query.offset((page - 1) * page_size)
            if page_size:
                query = query.limit(page_size)
            rows = query.all()
            
            result = []
            for row in rows:
                result_dict = {
                    "id": row.id,
                    "username": row.username,
                    "firstname": row.firstname,
                    "lastname": row.lastname,
                    "role": row.role,
                    "active": row.active,
                    "reset_password": row.reset_password,
                    "create_date": row.create_date,
                    "modify_date": row.modify_date,
                    "last_login": row.last_login
                }
                result.append(result_dict)
            return result, total_count, len(result)
        except Exception as ex:
            self.logger.error(f"{self._get_user_info()} Exception in list_users {ex}")
            raise
        finally:
            session.close()

