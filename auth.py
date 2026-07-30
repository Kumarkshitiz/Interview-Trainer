"""
V3: single-user auth. Every request must carry the shared secret in the
X-App-Secret header, checked against config.APP_SECRET.

V4 will replace this with a real users table + per-user token, but the
shape stays the same: a FastAPI dependency injected into every route.
Swapping this file out is the only change needed when that happens --
main.py's routes don't need to know how auth is implemented underneath.
"""

from fastapi import Header, HTTPException
from config import APP_SECRET


def require_auth(x_app_secret: str = Header(..., description="Shared app secret")):
    if x_app_secret != APP_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-App-Secret header.")