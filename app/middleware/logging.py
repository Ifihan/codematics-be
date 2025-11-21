from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import time
from app.core.logging_service import LoggingService


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        try:
            self.logging_service = LoggingService()
            self.enabled = True
        except Exception as e:
            print(f"Cloud Logging disabled: {e}")
            self.enabled = False

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        response = await call_next(request)

        duration_ms = (time.time() - start_time) * 1000

        if self.enabled:
            user_id = None
            if hasattr(request.state, "user"):
                user_id = request.state.user.id

            try:
                self.logging_service.log_api_request(
                    method=request.method,
                    path=request.url.path,
                    user_id=user_id,
                    status_code=response.status_code,
                    duration_ms=duration_ms
                )
            except Exception as e:
                print(f"Failed to log request: {e}")

        return response
