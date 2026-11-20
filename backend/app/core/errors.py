"""One error envelope for every failure: {"error": {"code", "message", "details"}}."""
import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger("smartspend")

_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    503: "SERVICE_UNAVAILABLE",
}


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details: list | None = None, headers: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details, self.headers = status, code, message, details or [], headers


def not_found(what: str = "Item") -> AppError:
    return AppError(404, "NOT_FOUND", f"{what} not found.")


def validation(message: str, field: str | None = None, issue: str = "invalid") -> AppError:
    return AppError(422, "VALIDATION_ERROR", message, [{"field": field, "issue": issue}] if field else [])


def _envelope(status: int, code: str, message: str, details: list | None = None, headers: dict | None = None):
    return JSONResponse({"error": {"code": code, "message": message, "details": details or []}}, status_code=status, headers=headers)


def _friendly(err: dict) -> tuple[str, str]:
    """Turn a pydantic error into (field, readable message)."""
    loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
    field = ".".join(loc) or "request"
    msg = err.get("msg", "Invalid value.")
    if msg.startswith("Value error, "):
        msg = msg[len("Value error, "):]
    return field, msg


def install(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return _envelope(exc.status, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(HTTPException)
    async def _http_error(_: Request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return _envelope(exc.status_code, _STATUS_CODES.get(exc.status_code, "ERROR"), message, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        details = []
        for err in exc.errors():
            field, msg = _friendly(err)
            details.append({"field": field, "issue": err.get("type", "invalid"), "message": msg})
        message = details[0]["message"] if len(details) == 1 else "Some fields need attention."
        return _envelope(422, "VALIDATION_ERROR", message, details)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        # Log the detail server-side only; never return stack traces or internals.
        log.exception("unhandled error", extra={"path": request.url.path})
        return _envelope(500, "INTERNAL_ERROR", "Something went wrong. Please try again.")
