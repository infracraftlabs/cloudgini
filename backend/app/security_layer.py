"""API keys, roles and rate limiting. Keys are compared by SHA-256 hash; plain keys never touch
the database, logs or responses."""
from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import get_settings

# Least privilege: admins manage settings and accounts but can't remediate; operators remediate
# but can't change settings. Nobody gets both unless you give them two keys.
PERMISSIONS: dict[str, set[str]] = {
    "viewer": {"read", "assistant"},
    "analyst": {"read", "assistant", "scan", "review"},
    "operator": {"read", "assistant", "scan", "review", "remediate"},
    "admin": {"read", "assistant", "scan", "manage"},
}


@dataclass(frozen=True)
class Principal:
    name: str
    role: str

    def can(self, perm: str) -> bool:
        return perm in PERMISSIONS.get(self.role, set())


def _keys() -> dict[str, Principal]:
    out = {}
    for entry in filter(None, (e.strip() for e in get_settings().api_keys.split(","))):
        name, role, digest = entry.split(":", 2)
        if role not in PERMISSIONS:
            raise ValueError(f"unknown role '{role}' for key '{name}'")
        out[digest.lower()] = Principal(name, role)
    return out


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


bearer = HTTPBearer(auto_error=False)


def current_principal(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Principal:
    if creds is None:
        raise HTTPException(401, "missing API key (Authorization: Bearer <key>)")
    digest = hash_key(creds.credentials)
    for known, p in _keys().items():
        if hmac.compare_digest(known, digest):
            return p
    raise HTTPException(401, "invalid API key")


def require(perm: str):
    def dep(p: Principal = Depends(current_principal)) -> Principal:
        if not p.can(perm):
            raise HTTPException(403, f"role '{p.role}' lacks the '{perm}' permission")
        return p
    return dep


class RateLimiter:
    """Sliding one-minute window per client (API key hash, else IP). In-memory: one instance per process."""

    SENSITIVE = ("/execute", "/assistant", "/scan", "/approve")

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, request: Request) -> None:
        s = get_settings()
        auth = request.headers.get("authorization", "")
        who = hash_key(auth)[:16] if auth else (request.client.host if request.client else "unknown")
        sensitive = request.method == "POST" and request.url.path.endswith(self.SENSITIVE)
        limit = s.sensitive_rate_limit_per_minute if sensitive else s.rate_limit_per_minute
        key = f"{who}|{'s' if sensitive else 'n'}"
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= limit:
                raise HTTPException(429, "rate limit exceeded, try again in a minute",
                                    headers={"Retry-After": str(int(60 - (now - q[0])) + 1)})
            q.append(now)


limiter = RateLimiter()
