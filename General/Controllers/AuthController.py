"""Authentication controller for login and token management."""
from http import HTTPStatus
from flask import Blueprint, request, jsonify
from typing import Any

from utils.logger_config import logger_method
from utils.jwt_utils import create_jwt_token, token_required
from General.Service.AuthService import AuthService

auth_bp = Blueprint('auth_bp', __name__)
logger = logger_method(__name__)


@auth_bp.post("/api/auth/login")
def login() -> Any:
    """Login endpoint to generate JWT token.
    
    Request body:
        {
            "username": "admin",
            "password": "admin123"
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
        data = request.get_json()
        
        if not data:
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": "Request body is required"
            }), HTTPStatus.BAD_REQUEST
        
        username = data.get("username")
        password = data.get("password")
        
        # Authenticate user
        is_authenticated, user_data, error = AuthService.authenticate_user(username, password)
        
        if not is_authenticated:
            return jsonify({
                "status": HTTPStatus.UNAUTHORIZED,
                "message": error or "Authentication failed"
            }), HTTPStatus.UNAUTHORIZED
        
        # Generate JWT token
        token = create_jwt_token(
            user_id=user_data["user_id"],
            username=user_data["username"],
            additional_claims={"role": user_data.get("role")}
        )
        
        return jsonify({
            "status": HTTPStatus.OK,
            "message": "Login successful",
            "data": {
                "token": token,
                "expires_in": 86400,  # 24 hours in seconds
                "user": user_data
            }
        }), HTTPStatus.OK
        
    except Exception as exc:
        logger.error(f"Login error: {str(exc)}", exc_info=True)
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
    user_claims = request.user_claims
    logger.info(f"User logged out: {user_claims['username']}")
    
    return jsonify({
        "status": HTTPStatus.OK,
        "message": "Logout successful"
    }), HTTPStatus.OK


@auth_bp.get("/api/auth/me")
@token_required
def get_current_user() -> Any:
    """Get current authenticated user info.
    
    Returns current user data from the JWT token.
    """
    user_claims = request.user_claims
    
    return jsonify({
        "status": HTTPStatus.OK,
        "message": "User data retrieved",
        "data": {
            "user_id": user_claims["user_id"],
            "username": user_claims["username"],
            "role": user_claims.get("role"),
            "expires_at": user_claims.get("exp")
        }
    }), HTTPStatus.OK


@auth_bp.post("/api/auth/register")
def register() -> Any:
    """Register a new user (optional endpoint).
    
    Request body:
        {
            "username": "newuser",
            "password": "password123"
        }
    
    Note: In production, add proper validation and security measures.
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": "Request body is required"
            }), HTTPStatus.BAD_REQUEST
        
        username = data.get("username")
        password = data.get("password")
        
        # Validate input
        if not username or not password:
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": "Username and password are required"
            }), HTTPStatus.BAD_REQUEST
        
        # Add user
        success, error = AuthService.add_user(username, password)
        
        if not success:
            return jsonify({
                "status": HTTPStatus.BAD_REQUEST,
                "message": error
            }), HTTPStatus.BAD_REQUEST
        
        return jsonify({
            "status": HTTPStatus.CREATED,
            "message": "User registered successfully",
            "data": {"username": username}
        }), HTTPStatus.CREATED
        
    except Exception as exc:
        logger.error(f"Registration error: {str(exc)}", exc_info=True)
        return jsonify({
            "status": HTTPStatus.INTERNAL_SERVER_ERROR,
            "message": "Registration failed"
        }), HTTPStatus.INTERNAL_SERVER_ERROR
