from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

EXEMPT_PATHS = {"/login", "/logout", "/run", "/api/health", "/healthz"}


def _is_exempt(path: str) -> bool:
    return path in EXEMPT_PATHS or path.startswith("/run")


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if _is_exempt(request.url.path):
            return await call_next(request)

        user = request.session.get("user")
        if not user:
            if request.url.path.startswith("/api/"):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Not authenticated"},
                )
            return RedirectResponse(url="/login", status_code=302)

        return await call_next(request)
