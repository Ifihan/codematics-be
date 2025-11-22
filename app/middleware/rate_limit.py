from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Dict, Tuple
import time
from collections import defaultdict
import asyncio


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, requests_per_minute: int = 100):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests: Dict[str, list] = defaultdict(list)
        self.cleanup_task = None

    async def dispatch(self, request: Request, call_next):
        # Start cleanup task if not running
        if self.cleanup_task is None:
            self.cleanup_task = asyncio.create_task(self._periodic_cleanup())

        if request.url.path in ["/health", "/docs", "/openapi.json", "/redoc"]:
            return await call_next(request)

        client_id = self._get_client_id(request)
        current_time = time.time()

        # Lazy cleanup on access (still good to keep for immediate consistency)
        self._cleanup_old_requests(client_id, current_time)

        if len(self.requests[client_id]) >= self.requests_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Maximum {self.requests_per_minute} requests per minute."
            )

        self.requests[client_id].append(current_time)

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(
            self.requests_per_minute - len(self.requests[client_id])
        )

        return response

    def _get_client_id(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _cleanup_old_requests(self, client_id: str, current_time: float):
        cutoff_time = current_time - 60
        self.requests[client_id] = [
            req_time for req_time in self.requests[client_id]
            if req_time > cutoff_time
        ]
        if not self.requests[client_id]:
            del self.requests[client_id]

    async def _periodic_cleanup(self):
        while True:
            await asyncio.sleep(60)
            current_time = time.time()
            cutoff_time = current_time - 60
            
            for client_id in list(self.requests.keys()):
                self.requests[client_id] = [
                    t for t in self.requests[client_id]
                    if t > cutoff_time
                ]
                if not self.requests[client_id]:
                    del self.requests[client_id]
