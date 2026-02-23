"""Authentication service for user login and token management."""
from typing import Optional, Tuple, Dict, Any
from utils.logger_config import logger_method
from Managers.UserManager import UserManager
from Managers.AuthManager import AuthManager
from Service.AuditLogService import AuditLogService
from DatabaseOperation.DatabaseModels.master_models import UserInput, UserUpdate
from utils.constants import AuditAction, default_password


class UserService:
    """Service for handling user authentication."""

    def __init__(self, user_claims: Optional[Dict[str, Any]] = None):
        self.logger = logger_method(__name__)
        self.user_claims = user_claims
        self.user_manager = UserManager(user_claims)
        self.auth_manager = AuthManager(user_claims)
        self.auditlog_service = AuditLogService(user_claims)

    def add_user(self, user_details: UserInput) -> Tuple[bool, Optional[str]]:
        try:
            if self.auth_manager.find_user(username=user_details.username, role=user_details.role):
                error_msg = f"User {user_details.username} already exists"
                user_id = self.user_claims.get('username') if self.user_claims else "admin"
                self.auditlog_service.record(
                    self.auditlog_service.build(
                        action_taken=AuditAction.INSERT_USER,
                        auto_manual="manual",
                        user_id=user_id,
                        payload={"status": "Failed", "details": error_msg, "request_object": user_details.__dict__}
                    )
                )
                return False, error_msg
            user_details.password = default_password
            result = self.user_manager.create(user_details)

            user_id = self.user_claims.get('username') if self.user_claims else "admin"
            self.auditlog_service.record(
                self.auditlog_service.build(
                    action_taken=AuditAction.INSERT_USER,
                    auto_manual="manual",
                    user_id=user_id,
                    payload={"status": "Success", "details": "User Created Successfully", "request_object": result}
                )
            )

            self.logger.info(f"New user added: {user_details.username}")
            return True, None
        except Exception as ex:
            user_id = self.user_claims.get('username') if self.user_claims else "admin"
            self.auditlog_service.record(
                self.auditlog_service.build(
                    action_taken=AuditAction.INSERT_USER,
                    auto_manual="manual",
                    user_id=user_id,
                    payload={"status": "Exception", "details": str(ex), "request_object": user_details.__dict__}
                )
            )
            raise ex

    def update(self, user_id: int, user_details: UserUpdate) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Update an existing user's details.

        Args:
            user_id: User id of the user to update
            user_details: UserInput object with fields to update

        Returns:
            Tuple of (success, error_message, updated_user_data)
        """
        try:
            result = self.user_manager.update(user_id, user_details)
            if result is None:
                error_msg = f"User {user_id} not found"
                self.logger.warning(error_msg)
                user_id_audit = self.user_claims.get('username') if self.user_claims else "system"
                self.auditlog_service.record(
                    self.auditlog_service.build(
                        action_taken=AuditAction.UPDATE_USER,
                        auto_manual="manual",
                        user_id=user_id_audit,
                        payload={"status": "Failed", "details": error_msg, "request_object": {"user_id": user_id}}
                    )
                )
                return False, error_msg, None

            user_id_audit = self.user_claims.get('username') if self.user_claims else "system"
            self.auditlog_service.record(
                self.auditlog_service.build(
                    action_taken=AuditAction.UPDATE_USER,
                    auto_manual="manual",
                    user_id=user_id_audit,
                    payload={"status": "Success", "details": "User Updated Successfully", "request_object": result}
                )
            )

            self.logger.info(f"User {user_id} updated successfully")
            return True, None, result
        except Exception as ex:
            user_id_audit = self.user_claims.get('username') if self.user_claims else "system"
            self.auditlog_service.record(
                self.auditlog_service.build(
                    action_taken=AuditAction.UPDATE_USER,
                    auto_manual="manual",
                    user_id=user_id_audit,
                    payload={"status": "Exception", "details": str(ex),
                             "request_object": {"user_id": user_id, "details": user_details.__dict__}}
                )
            )
            self.logger.error(f"Error updating user {user_id}: {str(ex)}")
            raise ex

    def list_users(
            self, active_only: bool = False, page_size: int = 10, page: int = 1, username: str = None, role: str = None
    ) -> tuple[list[dict[Any, Any] | dict[str, Any] | dict[str, str]], Any, Any]:
        """List user records with filtering and pagination.

        Args:
            active_only: If True, only return active users
            page: page number
            page_size: page size
            username: search string for username or firstname
            role: role to filter by

        Returns:
            Tuple of (list of user dicts, count)
        """
        try:
            results, total_count, rows = self.user_manager.list_users(
                active_only=active_only,
                page_size=page_size,
                page=page,
                username=username,
                role=role
            )
            self.logger.info(f"Retrieved {total_count} users")
            return results, total_count, rows
        except Exception as ex:
            self.logger.error(f"Error listing users: {str(ex)}")
            raise ex

    def set_password(self, username, new_password, reset_password) -> Tuple[bool, Optional[str]]:
        """Set a new password for the user."""
        try:
            result = self.user_manager.set_password(username, new_password, reset_password)
            if result is None:
                error_msg = f"User {username} not found"
                self.logger.warning(error_msg)
                user_id_audit = self.user_claims.get('username') if self.user_claims else "system"
                self.auditlog_service.record(
                    self.auditlog_service.build(
                        action_taken=AuditAction.RESET_PWD,
                        auto_manual="manual",
                        user_id=user_id_audit,
                        payload={"status": "Failed", "details": error_msg, "request_object": {"username": username}}
                    )
                )
                return False, error_msg

            user_id_audit = self.user_claims.get('username') if self.user_claims else "system"
            self.auditlog_service.record(
                self.auditlog_service.build(
                    action_taken=AuditAction.RESET_PWD,
                    auto_manual="manual",
                    user_id=user_id_audit,
                    payload={"status": "Success", "details": "Password Reset Successfully", "request_object": {"username": username}}
                )
            )

            self.logger.info(f"Password for user {username} reset successfully")
            return True, None
        except Exception as ex:
            user_id_audit = self.user_claims.get('username') if self.user_claims else "system"
            self.auditlog_service.record(
                self.auditlog_service.build(
                    action_taken=AuditAction.RESET_PWD,
                    auto_manual="manual",
                    user_id=user_id_audit,
                    payload={"status": "Exception", "details": str(ex), "request_object": {"username": username}}
                )
            )
            self.logger.error(f"Error resetting password for user {username}: {str(ex)}")
            raise ex