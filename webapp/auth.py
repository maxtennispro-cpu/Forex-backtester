"""Password hashing and the current-user dependency.

Hashing is stdlib PBKDF2 (no extra dependency); the stored format is
``pbkdf2$<iterations>$<salt_hex>$<hash_hex>``. Login state is the user id
in Starlette's signed session cookie.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3

from fastapi import Request

from . import db

_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"pbkdf2${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt_hex, hash_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


def current_user(request: Request) -> sqlite3.Row | None:
    """Resolve the logged-in user from the session cookie, if any."""
    user_id = request.session.get("user_id")
    if user_id is None:
        return None
    return db.get_user(user_id)
