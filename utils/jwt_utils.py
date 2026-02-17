"""JWT token utilities for authentication."""
import os
import jwt
import datetime as dt
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from functools import wraps
from flask import request, jsonify
from http import HTTPStatus
from utils.logger_config import logger_method

logger = logger_method(__name__)


class JWTConfig:
    """JWT configuration."""
    SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
    ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    EXPIRATION_HOURS: int = int(os.getenv("JWT_EXPIRATION_HOURS", "24"))


def create_jwt_token(user_id: int, username: str, additional_claims: Optional[Dict[str, Any]] = None) -> str:
    """Create a JWT token for a user.
    
    Args:
        user_id: User ID
        username: Username
        additional_claims: Additional claims to include in token
        
    Returns:
        Encoded JWT token
    """
    payload = {
        "user_id": user_id,
        "username": username,
        "iat": datetime.now(tz=dt.timezone.utc),
        "exp": datetime.now(tz=dt.timezone.utc) + timedelta(hours=JWTConfig.EXPIRATION_HOURS),
    }

    if additional_claims:
        payload.update(additional_claims)

    token = jwt.encode(payload, JWTConfig.SECRET_KEY, algorithm=JWTConfig.ALGORITHM)
    logger.info(f"JWT token created for user: {username}")
    return token


def verify_jwt_token(token: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
    """Verify a JWT token and extract claims.
    
    Args:
        token: JWT token to verify
        
    Returns:
        Tuple of (is_valid, claims_dict, error_message)
    """
    try:
        payload = jwt.decode(token, JWTConfig.SECRET_KEY, algorithms=[JWTConfig.ALGORITHM])
        return True, payload, None
    except jwt.ExpiredSignatureError:
        error_msg = "Token has expired"
        logger.warning(error_msg)
        return False, None, error_msg
    except jwt.InvalidTokenError as e:
        error_msg = f"Invalid token: {str(e)}"
        logger.warning(error_msg)
        return False, None, error_msg


def extract_token_from_request(request_obj: Any) -> Optional[str]:
    """Extract JWT token from Authorization header.
    
    Args:
        request_obj: Flask request object
        
    Returns:
        Token string or None
    """
    auth_header = request_obj.headers.get("Authorization")
    if not auth_header:
        return None

    try:
        # Expected format: "Bearer <token>"
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None
        return parts[1]
    except Exception as e:
        logger.warning(f"Error extracting token: {str(e)}")
        return None


def token_required(f):
    """Decorator to protect routes with JWT authentication.
    
    Usage:
        @app.route('/protected')
        @token_required
        def protected_route():
            current_user = request.user_claims
            return jsonify({"user": current_user["username"]})
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        token = extract_token_from_request(request)

        if not token:
            return jsonify({
                "status": HTTPStatus.UNAUTHORIZED,
                "message": "Missing authorization token"
            }), HTTPStatus.UNAUTHORIZED

        is_valid, claims, error = verify_jwt_token(token)

        if not is_valid:
            return jsonify({
                "status": HTTPStatus.UNAUTHORIZED,
                "message": error or "Invalid token"
            }), HTTPStatus.UNAUTHORIZED

        # Attach claims to request for use in route handler
        request.user_claims = claims
        return f(*args, **kwargs)

    return decorated
