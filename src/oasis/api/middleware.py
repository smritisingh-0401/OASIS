"""Security envelope applied to every response, including static files (rules P6)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
        "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def security_middleware(
    max_body_bytes: int,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Known limit: trusts Content-Length; uvicorn's h11 limits cover chunked bodies, and
        # the schema caps message length. Add a streaming byte counter if exposed publicly.
        length = request.headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > max_body_bytes):
            response: Response = error_response(413, "body_too_large", "Request is too large.")
        else:
            response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response

    return middleware
