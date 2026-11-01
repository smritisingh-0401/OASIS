"""Security envelope applied to every response, including static files (rules P6)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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
        # Fast path for an honest Content-Length; BodyLimit counts the bytes themselves.
        length = request.headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > max_body_bytes):
            response: Response = error_response(413, "body_too_large", "Request is too large.")
        else:
            response = await call_next(request)
        response.headers.update(SECURITY_HEADERS)
        return response

    return middleware


class BodyTooLarge(HTTPException):
    """An HTTP error, so FastAPI passes it through body parsing instead of turning it into a 400."""

    def __init__(self) -> None:
        super().__init__(413)


class BodyLimit:
    """Counts request body bytes as they arrive, so a chunked body without a Content-Length
    cannot exceed the limit either. The app maps BodyTooLarge to a 413."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        seen = 0

        async def counted() -> Message:
            nonlocal seen
            message = await receive()
            seen += len(message.get("body", b""))
            if seen > self.max_bytes:
                raise BodyTooLarge
            return message

        await self.app(scope, counted, send)
