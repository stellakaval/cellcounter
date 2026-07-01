"""JWT auth dependency — verifies Supabase-issued tokens."""
from __future__ import annotations

import base64
import json
import logging
import os
import urllib.request

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

# Module-level JWKS cache — fetched once on first request
_jwks_cache: dict | None = None


def _fetch_jwks(supabase_url: str) -> dict:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    url = f"{supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            _jwks_cache = json.loads(r.read())
            logger.info("Loaded Supabase JWKS from %s", url)
            return _jwks_cache
    except Exception as exc:
        logger.warning("Could not fetch JWKS from %s: %s", url, exc)
        return {}


def current_user(creds: HTTPAuthorizationCredentials | None = Security(security)) -> str:
    """Return the Supabase user UUID from the JWT, or raise 401.

    Supports both RS256 (newer Supabase projects, verified via JWKS) and
    HS256 (older projects, verified via JWT secret). Falls back to dev-user
    when neither secret nor URL is configured.
    """
    supabase_url = os.environ.get("SUPABASE_URL", "")
    secret = os.environ.get("SUPABASE_JWT_SECRET", "")

    if not supabase_url and not secret:
        return "dev-user"

    if creds is None:
        raise HTTPException(401, "Not authenticated")

    from jose import jwt as jose_jwt

    token = creds.credentials
    last_exc: Exception | None = None

    # Try JWKS first — Supabase uses ES256 (ECDSA P-256) for user tokens
    if supabase_url:
        try:
            jwks = _fetch_jwks(supabase_url)
            if jwks:
                payload = jose_jwt.decode(
                    token, jwks, algorithms=["ES256", "RS256"], audience="authenticated"
                )
                return str(payload["sub"])
        except Exception as exc:
            last_exc = exc
            logger.debug("RS256 verification failed: %s", exc)

    # Fall back to HS256 with the JWT secret
    if secret:
        try:
            try:
                key: bytes | str = base64.b64decode(secret)
            except Exception:
                key = secret
            payload = jose_jwt.decode(
                token, key, algorithms=["HS256"], audience="authenticated"
            )
            return str(payload["sub"])
        except Exception as exc:
            last_exc = exc
            logger.debug("HS256 verification failed: %s", exc)

    logger.warning("JWT verification failed: %s", last_exc)
    raise HTTPException(401, "Invalid token")
