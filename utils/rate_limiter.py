from flask import request
from flask_limiter import Limiter

def key_by_user_then_ip() -> str:
    claims = getattr(request, "user_claims", None)
    if claims and claims.get("username"):
        return f"user:{claims['username']}"
    return f"ip:{request.remote_addr}"

limiter = Limiter(
    key_func=key_by_user_then_ip,
    default_limits=["10 per minute"],   # your global default
    storage_uri="memory://",            # use Redis in prod
    headers_enabled=True,
)