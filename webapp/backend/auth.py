"""JWT auth dependency — verifies Supabase-issued tokens."""
from __future__ import annotations

import os

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

security = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Security(security)) -> str:
    """Return the Supabase user UUID from the JWT, or raise 401.

    When SUPABASE_JWT_SECRET is not set (local dev), returns "dev-user" so the app
    works without auth configured.
    """
    secret = os.environ.get("SUPABASE_JWT_SECRET", "")
    if not secret:
        # Dev mode: no secret configured — open access, single dev user.
        return "dev-user"
    if creds is None:
        raise HTTPException(401, "Not authenticated")
    try:
        from jose import jwt as jose_jwt

        payload = jose_jwt.decode(
            creds.credentials,
            secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return str(payload["sub"])
    except Exception:
        raise HTTPException(401, "Invalid token")
