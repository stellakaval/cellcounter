"""JWT auth dependency — verifies Supabase-issued tokens."""
from __future__ import annotations

import base64
import logging
import os

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials | None = Security(security)) -> str:
    """Return the Supabase user UUID from the JWT, or raise 401.

    When SUPABASE_JWT_SECRET is not set (local dev), returns "dev-user" so the app
    works without auth configured.
    """
    secret = os.environ.get("SUPABASE_JWT_SECRET", "")
    if not secret:
        return "dev-user"
    if creds is None:
        raise HTTPException(401, "Not authenticated")
    try:
        from jose import jwt as jose_jwt

        # Supabase's dashboard shows the JWT secret as a base64-encoded string.
        # Decode it to raw bytes so python-jose can verify the HMAC correctly.
        try:
            secret_bytes = base64.b64decode(secret)
        except Exception:
            secret_bytes = secret.encode()

        payload = jose_jwt.decode(
            creds.credentials,
            secret_bytes,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return str(payload["sub"])
    except Exception as exc:
        logger.warning("JWT verification failed: %s", exc)
        raise HTTPException(401, "Invalid token")
