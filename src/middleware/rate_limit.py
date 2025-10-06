"""
Rate limiting middleware for FastAPI
"""
import time
from collections import defaultdict, deque
from typing import Dict, Deque
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiting middleware"""
    
    def __init__(self, app, calls: int = 60, period: int = 60):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.clients: Dict[str, Deque[float]] = defaultdict(deque)
        
    def get_client_id(self, request: Request) -> str:
        """Get client identifier (IP address)"""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
    
    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path == "/health":
            return await call_next(request)
            
        client_id = self.get_client_id(request)
        now = time.time()
        
        # Clean old entries
        client_calls = self.clients[client_id]
        while client_calls and client_calls[0] <= now - self.period:
            client_calls.popleft()
        
        # Check rate limit
        if len(client_calls) >= self.calls:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Max {self.calls} requests per {self.period} seconds."
            )
        
        # Add current request
        client_calls.append(now)
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(self.calls)
        response.headers["X-RateLimit-Remaining"] = str(max(0, self.calls - len(client_calls)))
        response.headers["X-RateLimit-Reset"] = str(int(now + self.period))
        
        return response


class TranscriptionRateLimitMiddleware(BaseHTTPMiddleware):
    """Stricter rate limiting for transcription endpoints"""
    
    def __init__(self, app, calls: int = 10, period: int = 60):
        super().__init__(app)
        self.calls = calls
        self.period = period
        self.clients: Dict[str, Deque[float]] = defaultdict(deque)
        
    def get_client_id(self, request: Request) -> str:
        """Get client identifier (IP address)"""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"
    
    async def dispatch(self, request: Request, call_next):
        # Only apply to transcription endpoints
        if not request.url.path.startswith("/api/v1/transcribe"):
            return await call_next(request)
            
        client_id = self.get_client_id(request)
        now = time.time()
        
        # Clean old entries
        client_calls = self.clients[client_id]
        while client_calls and client_calls[0] <= now - self.period:
            client_calls.popleft()
        
        # Check rate limit
        if len(client_calls) >= self.calls:
            raise HTTPException(
                status_code=429,
                detail=f"Transcription rate limit exceeded. Max {self.calls} requests per {self.period} seconds."
            )
        
        # Add current request
        client_calls.append(now)
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers
        response.headers["X-Transcription-RateLimit-Limit"] = str(self.calls)
        response.headers["X-Transcription-RateLimit-Remaining"] = str(max(0, self.calls - len(client_calls)))
        response.headers["X-Transcription-RateLimit-Reset"] = str(int(now + self.period))
        
        return response