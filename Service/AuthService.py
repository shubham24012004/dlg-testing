"""Authentication service for user login and token management."""
from typing import Optional, Tuple, Dict, Any
from utils.logger_config import logger_method
from Managers.AuthManager import AuthManager
from Managers.UserManager import UserManager
from Service.AuditLogService import AuditLogService
from utils.constants import AuditAction


class AuthService:
    """Service for handling user authentication."""

    def __init__(self, user_claims: Optional[Dict[str, Any]] = None):
        self.logger = logger_method(__name__)
        self.user_claims = user_claims
        self.auth_manager = AuthManager(user_claims)
        self.use_manager = UserManager(user_claims)
        self.auditlog_service = AuditLogService(user_claims)

    def authenticate_user(self, username: str, password: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """Authenticate user with username and password.
        
        Args:
            username: Username
            password: Password
            role: Role
            
        Returns:
            Tuple of (is_authenticated, user_data_dict, error_message)
        """
        try:
            if not username or not password:
                error_msg = "Username and password are required"
                self.logger.warning(error_msg)
                user_id = username
                self.auditlog_service.record(
                    self.auditlog_service.build(
                        action_taken=AuditAction.LOGIN,
                        auto_manual="manual",
                        user_id=user_id,
                        payload={"status": "Failed", "details": error_msg, "request_object": {"username": username}}
                    )
                )
                return False, None, error_msg

            user = self.auth_manager.find_user_by_username(username=username)
            if not user:
                error_msg = f"User not found: {username}"
                self.logger.warning(error_msg)
                user_id = username
                self.auditlog_service.record(
                    self.auditlog_service.build(
                        action_taken=AuditAction.LOGIN,
                        auto_manual="manual",
                        user_id=user_id,
                        payload={"status": "Failed", "details": error_msg, "request_object": {"username": username}}
                    )
                )
                return False, None, error_msg

            if not user.password:
                error_msg = "User Password not found in DB. Please reset password."
                return False, None, error_msg

            if not self.auth_manager.verify_password(password, user.password):
                error_msg = "Invalid password"
                return False, None, error_msg

            self.logger.info(f"User authenticated successfully: {username}")
            self.use_manager.update_last_login(user.id)

            user_data = {
                "user_id": user.id,  # Simple user ID generation
                "username": user.username,
                "role": user.role,
                "reset_password": user.reset_password,
                "active": user.active
            }

            user_id = username
            self.auditlog_service.record(
                self.auditlog_service.build(
                    action_taken=AuditAction.LOGIN,
                    auto_manual="manual",
                    user_id=user_id,
                    payload={"status": "Success", "details": "User Login Successful", "request_object": user_data}
                )
            )

            self.logger.info(f"User authenticated: {username}")
            return True, user_data, None
        except Exception as ex:
            user_id = username
            self.auditlog_service.record(
                self.auditlog_service.build(
                    action_taken=AuditAction.LOGIN,
                    auto_manual="manual",
                    user_id=username,
                    payload={"status": "Exception", "details": str(ex), "request_object": {"username": username}}
                )
            )
            raise ex
