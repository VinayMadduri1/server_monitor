from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import current_app, g, jsonify, request


def create_token(username, role, secret, hours):
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=hours),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def require_auth(role=None):
    """Protect a route. Pass role='admin' to restrict it to admins (role-based access control)."""

    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            if not header.startswith("Bearer "):
                return jsonify(error="Missing or malformed Authorization header"), 401
            try:
                claims = jwt.decode(
                    header[len("Bearer "):],
                    current_app.config["SECRET_KEY"],
                    algorithms=["HS256"],
                )
            except jwt.ExpiredSignatureError:
                return jsonify(error="Token expired"), 401
            except jwt.InvalidTokenError:
                return jsonify(error="Invalid token"), 401
            if role and claims.get("role") != role:
                return jsonify(error="Forbidden: insufficient role"), 403
            g.user = claims
            return view(*args, **kwargs)

        return wrapper

    return decorator
