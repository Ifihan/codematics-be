from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.logging_service import LoggingService
import traceback
import sys


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            error_type = type(e).__name__
            error_message = str(e)
            trace = traceback.format_exc()

            print(f"Error: {error_type}: {error_message}", file=sys.stderr)
            print(trace, file=sys.stderr)

            try:
                logger = LoggingService()
                logger.log_error(
                    error_type=error_type,
                    error_message=error_message,
                    context={
                        "path": request.url.path,
                        "method": request.method,
                        "trace": trace
                    }
                )
            except Exception as log_error:
                print(f"Failed to log error: {log_error}", file=sys.stderr)

            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "error": error_type,
                    "message": error_message,
                    "path": request.url.path
                }
            )
