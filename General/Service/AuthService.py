"""Authentication service for user login and token management."""
from typing import Optional, Tuple, Dict, Any
from utils.logger_config import logger_method

logger = logger_method(__name__)


class AuthService:
    """Service for handling user authentication.
    
    Note: This is a basic implementation. In production, you should:
    - Store passwords securely using bcrypt or similar
    - Use a proper database (SQLAlchemy models)
    - Implement refresh tokens
    - Add rate limiting
    """
    
    # Hardcoded users for demo - replace with database lookup
    VALID_USERS = {
        "admin": "admin123",  # username: password
        "user": "password123",
    }
    
    @classmethod
    def authenticate_user(cls, username: str, password: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """Authenticate user with username and password.
        
        Args:
            username: Username
            password: Password
            
        Returns:
            Tuple of (is_authenticated, user_data_dict, error_message)
        """
        if not username or not password:
            error_msg = "Username and password are required"
            logger.warning(error_msg)
            return False, None, error_msg
        
        # In production: hash password and compare with database
        stored_password = cls.VALID_USERS.get(username)
        if not stored_password or stored_password != password:
            error_msg = f"Invalid credentials for user: {username}"
            logger.warning(error_msg)
            return False, None, error_msg
        
        # User authenticated successfully
        user_data = {
            "user_id": hash(username) % (10**8),  # Simple user ID generation
            "username": username,
            "role": "admin" if username == "admin" else "user",
        }
        
        logger.info(f"User authenticated: {username}")
        return True, user_data, None
    
    @classmethod
    def add_user(cls, username: str, password: str) -> Tuple[bool, Optional[str]]:
        """Add a new user (for demo purposes only).
        
        In production, this should:
        - Validate username/password strength
        - Hash the password
        - Store in database
        - Implement proper error handling
        """
        if username in cls.VALID_USERS:
            return False, f"User {username} already exists"
        
        if len(password) < 6:
            return False, "Password must be at least 6 characters"
        
        cls.VALID_USERS[username] = password
        logger.info(f"New user added: {username}")
        return True, None
