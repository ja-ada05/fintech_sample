"""Minimal signed-token auth for the backend (users table in MySQL).

Note on Auth.js: it targets server frameworks (Next.js/SvelteKit) and is awkward
on a pure Vite SPA. The pragmatic split is this FastAPI-issued token consumed by
a thin client wrapper, or an Auth.js credentials provider pointed at
``POST /api/auth/login``. This module is the token issuing/verifying side and can
be swapped for real JWTs (PyJWT) later.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import database

SECRET = os.environ.get("JWT_SECRET", "change-me-in-prod")
TOKEN_TTL = int(os.environ.get("JWT_TTL", str(8 * 3600)))

USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS credit.users (
    user_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(128) NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'analyst',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _hash(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
    return f"{salt}${digest}"


def hash_password(password: str) -> str:
    return _hash(password, os.urandom(16).hex())


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, _ = stored.split("$", 1)
    except ValueError:
        return False
    return hmac.compare_digest(_hash(password, salt), stored)


def _b64(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_token(username: str, role: str) -> str:
    payload = {"sub": username, "role": role, "exp": int(time.time()) + TOKEN_TTL}
    body = _b64(json.dumps(payload).encode())
    sig = _b64(hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def decode_token(token: str) -> dict:
    try:
        body, sig = token.split(".", 1)
        expect = _b64(hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expect):
            raise ValueError("bad signature")
        payload = json.loads(_unb64(body))
        if int(payload.get("exp", 0)) < time.time():
            raise ValueError("token expired")
        return payload
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token ({exc})") from exc


def ensure_users_table() -> None:
    conn = database.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(USERS_TABLE_SQL)
        conn.commit()
    finally:
        conn.close()


def seed_default_admin(username: str = "admin", password: str = "admin123") -> None:
    conn = database.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM credit.users")
            if cur.fetchone()["n"] == 0:
                cur.execute(
                    "INSERT INTO credit.users (username, password_hash, role) VALUES (%s, %s, %s)",
                    (username, hash_password(password), "admin"),
                )
                conn.commit()
    finally:
        conn.close()


def authenticate(username: str, password: str) -> dict | None:
    conn = database.get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT username, password_hash, role FROM credit.users WHERE username = %s",
                (username,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row or not verify_password(password, row["password_hash"]):
        return None
    return row


_bearer = HTTPBearer(auto_error=False)


def get_current_user(cred: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> dict:
    if cred is None:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    return decode_token(cred.credentials)
