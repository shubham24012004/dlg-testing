## Default Credentials

For testing, the following users are pre-configured in `AuthService.VALID_USERS`:

| Username | Password | Role |
|----------|----------|------|
| admin | admin123 | admin |
| user | password123 | user |

**⚠️ WARNING: Replace with proper database-backed authentication in production!**

## Production Considerations

### 1. Password Security
Current implementation stores passwords in plain text. Replace with:
```python
from werkzeug.security import generate_password_hash, check_password_hash

# Hashing passwords
hashed = generate_password_hash(password, method='pbkdf2:sha256')

# Verifying passwords
check_password_hash(hashed, password)
```

### 2. Database Integration
Replace `AuthService.VALID_USERS` dict with SQLAlchemy models:

```python
from DatabaseOperation.DatabaseModels.master_models import Base, User


class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), default='user')
```

### 3. Token Blacklisting
For logout functionality, implement token blacklisting:

```python
# Store revoked tokens in Redis or database
BLACKLISTED_TOKENS = set()

def logout():
    token = extract_token_from_request(request)
    BLACKLISTED_TOKENS.add(token)
    return jsonify({"message": "Logged out"})

def verify_jwt_token(token):
    if token in BLACKLISTED_TOKENS:
        return False, None, "Token has been revoked"
    # ... rest of verification
```

### 4. Refresh Tokens
Implement refresh tokens for better security:

```python
def create_tokens(user_id, username):
    access_token = create_jwt_token(user_id, username, 
                                    expiration_hours=1)
    refresh_token = create_jwt_token(user_id, username,
                                     expiration_hours=7*24)
    return access_token, refresh_token
```

### 5. Rate Limiting
Add rate limiting to prevent brute force attacks:

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(app, key_func=get_remote_address)

@auth_bp.post("/api/auth/login")
@limiter.limit("5 per minute")
def login():
    # ...
```

### 6. HTTPS Only
In production, enforce HTTPS:
```python
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
```

### 7. Secret Key Management
Use a secure method to store JWT_SECRET_KEY:
- AWS Secrets Manager
- HashiCorp Vault
- Environment variables from CI/CD pipeline
- Never commit to version control

## Protecting Existing Routes

To protect your existing routes (e.g., `/api/scrape`), add the `@token_required` decorator:

```python
from utils.jwt_utils import token_required
from flask import request

@crawler_bp.post("/api/scrape")
@token_required
def handle_trigger_scrape():
    """Handle manual scrape trigger request."""
    user_claims = request.user_claims  # Access logged-in user
    lsp_id = request.args.get("lsp_id", default=0, type=int)
    
    # ... rest of implementation
```

## Troubleshooting

### Token Validation Fails
- Check `JWT_SECRET_KEY` is the same on all servers
- Verify token hasn't expired (check `exp` claim)
- Ensure `Authorization` header format is correct: `Bearer <token>`

### 401 Unauthorized Errors
- Verify you're sending the token in the `Authorization` header
- Check token expiration (default: 24 hours)
- Validate credentials in login request

### Token Decode Errors
- Verify `JWT_ALGORITHM` matches token encoding
- Ensure `JWT_SECRET_KEY` hasn't changed
- Check token hasn't been tampered with

## Security Checklist

- [ ] Change `JWT_SECRET_KEY` to a strong random value
- [ ] Never commit secrets to version control
- [ ] Use HTTPS in production
- [ ] Implement password hashing with bcrypt
- [ ] Replace in-memory user storage with database
- [ ] Add rate limiting to login endpoint
- [ ] Implement token blacklisting for logout
- [ ] Use refresh tokens for long-lived sessions
- [ ] Add audit logging for authentication events
- [ ] Implement CORS properly for production
- [ ] Add unit tests for auth functions
- [ ] Implement refresh token rotation
