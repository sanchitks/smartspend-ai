"""Password hashing (Argon2id), access tokens (JWT), rate limiting and request-level middleware."""
import json
import logging
import threading
import time
import uuid
from collections import OrderedDict, deque
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Request

from app.core.config import get_settings
from app.core.errors import AppError

# ---------------------------------------------------------------- passwords

_hasher = PasswordHasher()  # Argon2id with the library's recommended parameters
_DUMMY_HASH = _hasher.hash("timing-equaliser")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-ish time: a missing user still costs one Argon2 verification."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


# ---------------------------------------------------------------- access tokens

ALGORITHM = "HS256"


def create_access_token(user_id: int, session_id: str) -> tuple[str, datetime]:
    s = get_settings()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=s.jwt_access_token_expire_minutes)
    payload = {"sub": str(user_id), "sid": session_id, "iat": now, "exp": expires, "typ": "access"}
    return jwt.encode(payload, s.jwt_secret_key, algorithm=ALGORITHM), expires


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(
            token, get_settings().jwt_secret_key, algorithms=[ALGORITHM], options={"require": ["exp", "sub", "sid"]}
        )
    except jwt.ExpiredSignatureError as exc:
        raise AppError(401, "TOKEN_EXPIRED", "Your session has expired. Please log in again.") from exc
    except jwt.PyJWTError as exc:
        raise AppError(401, "UNAUTHORIZED", "Please log in.") from exc
    if payload.get("typ") != "access":
        raise AppError(401, "UNAUTHORIZED", "Please log in.")
    return payload


# ---------------------------------------------------------------- rate limiting


class RateLimiter:
    """In-memory sliding window per key. Bounded so it can't grow without limit.

    Fine for one API process; use Redis or the platform's limiter when running several.
    """

    def __init__(self, limit: int, window_seconds: int, max_keys: int = 10_000):
        self.limit, self.window, self.max_keys = limit, window_seconds, max_keys
        self._hits: OrderedDict[str, deque] = OrderedDict()
        self._lock = threading.Lock()

    def hit(self, key: str) -> int | None:
        """Record a hit. Returns None if allowed, otherwise seconds until the next slot frees up."""
        now = time.monotonic()
        with self._lock:
            q = self._hits.get(key)
            if q is None:
                q = self._hits[key] = deque()
                while len(self._hits) > self.max_keys:
                    self._hits.popitem(last=False)
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return int(self.window - (now - q[0])) + 1
            q.append(now)
            self._hits.move_to_end(key)
            return None

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def enforce(limiter: RateLimiter, key: str, message: str = "Too many requests. Please wait and try again.") -> None:
    wait = limiter.hit(key)
    if wait is not None:
        raise AppError(429, "RATE_LIMITED", message, headers={"Retry-After": str(wait)})


# ---------------------------------------------------------------- logging and middleware

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class JsonFormatter(logging.Formatter):
    """Structured logs. Only fields we choose are written: no request bodies, no financial text."""

    SAFE_EXTRAS = ("path", "method", "status", "duration_ms", "user_id", "intent", "provider", "model", "node", "error_type")

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for key in self.SAFE_EXTRAS:
            if hasattr(record, key):
                data[key] = getattr(record, key)
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("smartspend")
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    root.propagate = False


SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cache-control", b"no-store"),  # financial data must not sit in shared caches
    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
]
MAX_BODY_BYTES = 1_000_000  # 1 MB covers CSV imports; everything else is far smaller


class RequestContextMiddleware:
    """Plain ASGI middleware: request IDs, access logs, security headers and a request-size cap."""

    def __init__(self, app):
        self.app = app
        self.log = logging.getLogger("smartspend.access")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers") or [])
        incoming = headers.get(b"x-request-id", b"").decode("latin-1")
        rid = incoming if incoming and len(incoming) <= 64 and incoming.replace("-", "").isalnum() else uuid.uuid4().hex
        token = request_id_var.set(rid)
        started = time.perf_counter()
        status_holder = {"status": 500}

        length = headers.get(b"content-length")
        if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
            body = json.dumps({"error": {"code": "PAYLOAD_TOO_LARGE", "message": "Request is too large.", "details": []}}).encode()
            await send({"type": "http.response.start", "status": 413,
                        "headers": [(b"content-type", b"application/json"), (b"x-request-id", rid.encode())]})
            await send({"type": "http.response.body", "body": body})
            request_id_var.reset(token)
            return

        received = 0

        async def capped_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > MAX_BODY_BYTES:
                    raise AppError(413, "PAYLOAD_TOO_LARGE", "Request is too large.")
            return message

        is_docs_page = scope.get("path") in ("/docs", "/redoc", "/docs/oauth2-redirect")

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                existing = {k.lower() for k, _ in message.get("headers", [])}
                # The interactive docs page loads Swagger UI, so it skips the API's deny-all CSP.
                extra = [(k, v) for k, v in SECURITY_HEADERS
                         if k not in existing and not (is_docs_page and k == b"content-security-policy")]
                message["headers"] = list(message.get("headers", [])) + extra + [(b"x-request-id", rid.encode())]
            await send(message)

        try:
            await self.app(scope, capped_receive, send_with_headers)
        finally:
            self.log.info(
                "request",
                extra={
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": status_holder["status"],
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            request_id_var.reset(token)
