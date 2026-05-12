"""User Management controller for User management."""
from http import HTTPStatus
from flask import Blueprint, request, jsonify
from typing import Any

from utils.logger_config import logger_method
from utils.jwt_utils import token_required
from Service.UserService import UserService
from DatabaseOperation.DatabaseModels.master_models import UserInput, UserUpdate
from utils.constants import default_password
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from utils.rate_limiter import limiter

user_bp = Blueprint('user_bp', __name__)
logger = logger_method(__name__)


@user_bp.post("/api/user")
@token_required
@limiter.limit("5 per minute")
def add_user() -> Any:
    """Register a new user
    Request body:
        {
            "username": "newuser@email.com",
            "password": "password123",
            "role": "user/admin",
            "firstname": "firstname"
        }
    """
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"

    if user_role != 'admin':
        return jsonify(
            {"status": HTTPStatus.UNAUTHORIZED, "message": 'Not Allowed to Delete LSP',
             "user_info": user_info}), HTTPStatus.UNAUTHORIZED

    try:
        data = request.get_json(silent=True)

        if not data:
            logger.info(f"{user_info} Register attempt with no request body")
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": "Request body is required",
                "user_info": user_info
            }), HTTPStatus.BAD_REQUEST

        user_input = UserInput(**data)
        # Validate input
        if not user_input.username or not user_input.role or not user_input.firstname:
            logger.info(f"{user_info} Register attempt with missing required fields")
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": "Username, password, role and firstname are required",
                "user_info": user_info
            }), HTTPStatus.BAD_REQUEST

        # todo: check if user name is a valid email using regex.

        # Add user
        user_service = UserService(user_claims)
        success, error = user_service.add_user(user_details=user_input)

        if not success:
            logger.warning(f"{user_info} Failed to register user {user_input.username}: {error}")
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": error,
                "user_info": user_info
            }), HTTPStatus.BAD_REQUEST

        logger.info(f"{user_info} Successfully registered new user {user_input.username}")
        return jsonify({
            "status": HTTPStatus.CREATED,
            "message": "User registered successfully",
            "user_info": user_info,
            "data": {"username": user_input.username}
        }), HTTPStatus.CREATED

    except Exception as exc:
        logger.critical(f"{user_info} Registration error: {str(exc)}", exc_info=True)
        return jsonify({
            "status": HTTPStatus.INTERNAL_SERVER_ERROR,
            "message": "Registration failed",
            "user_info": user_info
        }), HTTPStatus.INTERNAL_SERVER_ERROR


@user_bp.put("/api/user")
@token_required
@limiter.limit("5 per minute")
def update_user() -> Any:
    """Update user details.
    
    Request body:
        {
            username: str
            role: str
            id: int
            password: Optional[str] = None
            firstname: Optional[str] = None
            lastname: Optional[str] = None
            reset_password: Optional[bool] = None
            active: Optional[bool] = None
        }
    """
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"
    user_id = user_claims.get('user_id')

    if user_role != 'admin':
        return jsonify(
            {"status": HTTPStatus.UNAUTHORIZED, "message": 'Not Allowed to Delete LSP',
             "user_info": user_info}), HTTPStatus.UNAUTHORIZED

    try:
        data = request.get_json(silent=True)

        if not data:
            logger.info(f"{user_info} Update user attempt with no request body")
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": "Request body is required",
                "user_info": user_info
            }), HTTPStatus.BAD_REQUEST

        user_input = UserUpdate(**data)

        # Update user
        user_service = UserService(user_claims)
        success, error, result = user_service.update(user_input.id, user_details=user_input)

        if not success:
            logger.warning(f"{user_info} Failed to update user {user_id}: {error}")
            return jsonify({
                "status": HTTPStatus.NOT_FOUND,
                "message": error,
                "user_info": user_info
            }), HTTPStatus.NOT_FOUND

        logger.info(f"{user_info} Successfully updated user {user_id}")
        return jsonify({
            "status": HTTPStatus.OK,
            "message": "User updated successfully",
            "user_info": user_info,
            "data": result
        }), HTTPStatus.OK

    except Exception as exc:
        logger.critical(f"{user_info} Update user error: {str(exc)}", exc_info=True)
        return jsonify({
            "status": HTTPStatus.INTERNAL_SERVER_ERROR,
            "message": "Update failed",
            "user_info": user_info
        }), HTTPStatus.INTERNAL_SERVER_ERROR


@user_bp.post("/api/user/update-password")
@token_required
@limiter.limit("5 per minute")
def update_password() -> Any:
    """Reset user password.
    
    Request body:
        {
            "username": "username"
            "password": "newpassword"
        }
    """
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"

    try:
        data = request.get_json(silent=True)

        if not data:
            logger.info(f"{user_info} Reset password attempt with no request body")
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": "Request body is required",
                "user_info": user_info
            }), HTTPStatus.BAD_REQUEST

        username = data.get("username")
        new_password = data.get("password")

        if not username or not new_password:
            logger.info(f"{user_info} Reset password attempt with missing user_id/password")
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": "Password is required",
                "user_info": user_info
            }), HTTPStatus.BAD_REQUEST

        # Reset password
        user_service = UserService(user_claims)
        hashed_password = user_service.auth_manager.hash_password(new_password)
        success, error = user_service.set_password(username, hashed_password, reset_password=False)

        if not success:
            logger.warning(f"{user_info} Failed to reset password for user {username}: {error}")
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": error,
                "user_info": user_info
            }), HTTPStatus.BAD_REQUEST

        logger.info(f"{user_info} Successfully reset password for user {username}")
        return jsonify({
            "status": HTTPStatus.OK,
            "message": "Password reset successfully",
            "user_info": user_info,
            "data": None
        }), HTTPStatus.OK

    except Exception as exc:
        logger.critical(f"{user_info} Reset password error: {str(exc)}", exc_info=True)
        return jsonify({
            "status": HTTPStatus.INTERNAL_SERVER_ERROR,
            "message": "Password reset failed",
            "user_info": user_info
        }), HTTPStatus.INTERNAL_SERVER_ERROR


@user_bp.post("/api/user/reset-password")
@limiter.limit("1 per minute")
def reset_password() -> Any:
    """Reset user password.

    Request body:
        {
            "username": "username"
            "password": "newpassword"
        }
    """
    user_info = "User: Reset_User, Role: User_role"

    try:
        data = request.get_json(silent=True)
        if not data:
            logger.info(f"{user_info} Reset password attempt with no username")
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": "Request body is required",
                "user_info": user_info
            }), HTTPStatus.BAD_REQUEST

        if not data['username']:
            logger.info(f"{user_info} Reset password attempt with no username")
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": "Request body is required",
                "user_info": user_info
            }), HTTPStatus.BAD_REQUEST

        # Reset password
        user_service = UserService()
        hashed_password = default_password
        success, error = user_service.set_password(data['username'], hashed_password, reset_password=True)

        if not success:
            logger.warning(f"{user_info} Failed to reset password for user {data['username']}: {error}")
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": error,
                "user_info": user_info
            }), HTTPStatus.BAD_REQUEST

        logger.info(f"{user_info} Successfully reset password for user {data['username']}")
        return jsonify({
            "status": HTTPStatus.OK,
            "message": "Password reset successfully",
            "user_info": user_info,
            "data": None
        }), HTTPStatus.OK

    except Exception as exc:
        logger.critical(f"{user_info} Reset password error: {str(exc)}", exc_info=True)
        return jsonify({
            "status": HTTPStatus.INTERNAL_SERVER_ERROR,
            "message": "Password reset failed",
            "user_info": user_info
        }), HTTPStatus.INTERNAL_SERVER_ERROR


@user_bp.get("/api/users")
@limiter.limit("10 per minute")
@token_required
def list_users() -> Any:
    """List all users with filtering and pagination.
    
    Query parameters:
        - active: boolean (default=True) - filter by active status
        - page: integer (default=1) - page number
        - pagesize: integer (default=10) - items per page
        - name: string - filter by username or firstname
        - role: string - filter by role
    
    Returns:
        {
            "status": 200,
            "message": "Users fetched successfully",
            "data": [...],
            "count": 5,
            "user_info": "[User: admin, Role: admin]"
        }
    """
    user_claims = request.user_claims
    username = user_claims['username']
    user_role = user_claims.get('role', 'unknown')
    user_info = f"[User: {username}, Role: {user_role}]"
    if user_role != 'admin':
        return jsonify(
            {"status": HTTPStatus.UNAUTHORIZED, "message": 'Not Allowed to Delete LSP',
             "user_info": user_info}), HTTPStatus.UNAUTHORIZED

    try:
        active = request.args.get('active', default="True", type=str)
        active_flag = True
        if active.lower() == "false":
            active_flag = False
        page = request.args.get('page', default=1, type=int)
        pagesize = request.args.get('pagesize', default=10, type=int)
        name = request.args.get('name', default="", type=str)
        role = request.args.get('role', default="", type=str)

        user_service = UserService(user_claims)
        results, total_count, rows = user_service.list_users(
            active_only=active_flag,
            page=page,
            page_size=pagesize,
            username=name if name else None,
            role=role if role else None
        )

        logger.info(f"{user_info} Fetched Users: {total_count}")

        if total_count > 0:
            return jsonify({
                "status": HTTPStatus.OK,
                "message": "Users fetched successfully",
                "user_info": user_info,
                "data": results,
                "count": total_count
            }), HTTPStatus.OK
        else:
            logger.info(f"{user_info} No users found")
            return jsonify({
                "status": HTTPStatus.NOT_FOUND,
                "message": "No users found",
                "user_info": user_info,
                "count": 0
            }), HTTPStatus.NOT_FOUND

    except Exception as exc:
        logger.critical(f"{user_info} Error listing users: {str(exc)}", exc_info=True)
        return jsonify({
            "status": HTTPStatus.INTERNAL_SERVER_ERROR,
            "message": str(exc),
            "user_info": user_info
        }), HTTPStatus.INTERNAL_SERVER_ERROR
