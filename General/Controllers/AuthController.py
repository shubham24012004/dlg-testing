"""Authentication controller for login and token management."""
from http import HTTPStatus
from flask import Blueprint, request, jsonify
from typing import Any

from utils.logger_config import logger_method
from utils.jwt_utils import create_jwt_token, token_required
from General.Service.AuthService import AuthService
from DatabaseOperation.DatabaseModels.master_models import UserInput

auth_bp = Blueprint('auth_bp', __name__)
logger = logger_method(__name__)


@auth_bp.post("/api/auth/login")
def login() -> Any:
    """Login endpoint to generate JWT token.

    Request body:
        {
            "username": "admin",
            "password": "admin123"
            "role": "admin"
        }

    Returns:
        {
            "status": 200,
            "message": "Login successful",
            "data": {
                "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
                "expires_in": 86400,
                "user": {"username": "admin", "user_id": 123, "role": "admin"}
            }
        }
    """
    try:
        data = request.get_json(silent=True)

        if not data:
            logger.info("Login attempt with no request body")
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": "Request body is required"
            }), HTTPStatus.BAD_REQUEST

        username = (data.get("username") or "").strip()
        password = data.get("password") or ""
        
        user_info = f"[User: {username or 'unknown'}, Role: unknown]"

        if not username or not password:
            logger.info(f"{user_info} Login attempt with missing required fields")
            return jsonify({
                "status": int(HTTPStatus.BAD_REQUEST),
                "message": "Username and password are required",
                "user_info": user_info
            }), HTTPStatus.BAD_REQUEST
        
        # Authenticate user
        auth_service = AuthService()
        is_authenticated, user_data, error = auth_service.authenticate_user(username=username,
                                                                            password=password)

        if not is_authenticated:
            logger.info(f"{user_info} Login failed: {error}")
            return jsonify({
                "status": int(HTTPStatus.UNAUTHORIZED),
                "message": error or "Authentication failed"
            }), HTTPStatus.UNAUTHORIZED

        # Generate JWT token
        token = create_jwt_token(
            user_id=user_data["user_id"],
            username=user_data["username"],
            additional_claims={"role": user_data.get("role")}
        )
        user_info = f"[User: {user_data['username']}, Role: {user_data.get('role', 'unknown')}]"
        logger.info(f"{user_info} User logged in successfully")
        return jsonify({
            "status": int(HTTPStatus.OK),
            "message": "Login successful",
            "data": {
                "token": token,
                "expires_in": 86400,  # 24 hours in seconds
                "user": user_data
            }
        }), HTTPStatus.OK

    except Exception as exc:
        logger.critical(f"Login error: {str(exc)}", exc_info=True)
        return jsonify({
            "status": HTTPStatus.INTERNAL_SERVER_ERROR,
            "message": "Login failed"
        }), HTTPStatus.INTERNAL_SERVER_ERROR


@auth_bp.post("/api/auth/logout")
@token_required
def logout() -> Any:
    """Logout endpoint (invalidates token on client side).

    JWT tokens are stateless, so logout is handled client-side by discarding the token.
    This endpoint can be used for audit logging or token blacklisting if needed.
    """
    try:
        user_claims = request.user_claims
        username = user_claims['username']
        user_role = user_claims.get('role', 'unknown')
        user_info = f"[User: {username}, Role: {user_role}]"

        logger.info(f"{user_info} User logged out successfully")

        return jsonify({
            "status": HTTPStatus.OK,
            "message": "Logout successful",
            "user_info": user_info
        }), HTTPStatus.OK
    except Exception as exc:
        logger.critical(f"Logout error: {str(exc)}", exc_info=True)
        return jsonify({
            "status": HTTPStatus.INTERNAL_SERVER_ERROR,
            "message": "Logout failed"
        }), HTTPStatus.INTERNAL_SERVER_ERROR


@auth_bp.get("/api/auth/me")
@token_required
def get_current_user() -> Any:
    """Get current authenticated user info.

    Returns current user data from the JWT token.
    """
    try:
        user_claims = request.user_claims
        username = user_claims['username']
        user_role = user_claims.get('role', 'unknown')
        user_info = f"[User: {username}, Role: {user_role}]"

        logger.info(f"{user_info} Retrieved current user info")

        return jsonify({
            "status": HTTPStatus.OK,
            "message": "User data retrieved",
            "user_info": user_info,
            "data": {
                "user_id": user_claims["user_id"],
                "username": user_claims["username"],
                "role": user_claims.get("role"),
                "expires_at": user_claims.get("exp")
            }
        }), HTTPStatus.OK
    except Exception as exc:
        logger.critical(f"Error retrieving current user: {str(exc)}", exc_info=True)
        return jsonify({
            "status": HTTPStatus.INTERNAL_SERVER_ERROR,
            "message": "Failed to retrieve user data"
        }), HTTPStatus.INTERNAL_SERVER_ERROR
