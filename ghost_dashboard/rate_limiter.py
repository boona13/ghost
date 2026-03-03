"""Rate limiter for dashboard API endpoints.

Provides token bucket rate limiting with per-IP tracking.
Usage:
    from ghost_dashboard.rate_limiter import rate_limit

    @bp.route("/api/expensive")
    @rate_limit(requests_per_minute=10)
    def expensive_endpoint():
        ...
"""

import time
import threading
import logging
from functools import wraps
from flask import request, jsonify

log = logging.getLogger(__name__)


class TokenBucket:
    """Token bucket rate limiter for a single client."""

    def __init__(self, capacity: int, refill_rate: float):
        """
        Args:
            capacity: Maximum number of tokens (burst capacity)
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.tokens = float(capacity)
        self.refill_rate = refill_rate
        self.last_update = time.time()
        self.lock = threading.Lock()

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume tokens. Returns True if allowed, False if rate limited."""
        with self.lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
            self.last_update = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def retry_after(self) -> int:
        """Seconds until enough tokens are available for 1 request."""
        with self.lock:
            if self.tokens >= 1:
                return 0
            needed = 1 - self.tokens
            return int(needed / self.refill_rate) + 1


class RateLimiter:
    """In-memory rate limiter with per-key token buckets."""

    def __init__(self):
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def get_bucket(self, key: str, capacity: int, refill_rate: float) -> TokenBucket:
        """Get or create a token bucket for the given key."""
        with self._lock:
            if key not in self._buckets:
                self._buckets[key] = TokenBucket(capacity, refill_rate)
            return self._buckets[key]

    def is_allowed(self, key: str, capacity: int, refill_rate: float) -> tuple[bool, int]:
        """Check if request is allowed. Returns (allowed, retry_after_seconds)."""
        bucket = self.get_bucket(key, capacity, refill_rate)
        allowed = bucket.consume(1)
        retry_after = bucket.retry_after() if not allowed else 0
        return allowed, retry_after

    def cleanup_old_buckets(self, max_age_seconds: float = 3600):
        """Remove buckets that haven't been used recently."""
        now = time.time()
        with self._lock:
            stale_keys = [
                key for key, bucket in self._buckets.items()
                if now - bucket.last_update > max_age_seconds
            ]
            for key in stale_keys:
                del self._buckets[key]


# Global rate limiter instance
_limiter = RateLimiter()


def _get_client_ip() -> str:
    """Extract client IP from request, handling proxies."""
    # Check X-Forwarded-For header first (for proxies)
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        # Take the first IP in the chain
        return forwarded.split(',')[0].strip()
    # Fall back to direct remote address
    return request.remote_addr or 'unknown'


def rate_limit(requests_per_minute: int = 60, key_func=None):
    """Decorator to apply rate limiting to a Flask route.

    Args:
        requests_per_minute: Maximum requests allowed per minute
        key_func: Optional function to extract rate limit key from request.
                 Defaults to per-IP limiting.

    Example:
        @bp.route("/api/chat", methods=["POST"])
        @rate_limit(requests_per_minute=10)
        def chat_endpoint():
            ...
    """
    capacity = requests_per_minute
    refill_rate = requests_per_minute / 60.0  # tokens per second

    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            # Get rate limit key
            if key_func:
                key = key_func(request)
            else:
                key = _get_client_ip()

            # Add endpoint name to key for per-endpoint limiting
            endpoint_key = f"{f.__name__}:{key}"

            allowed, retry_after = _limiter.is_allowed(
                endpoint_key, capacity, refill_rate
            )

            if not allowed:
                log.warning(
                    "Rate limit exceeded for %s from %s",
                    f.__name__, key
                )
                response = jsonify({
                    "error": "Rate limit exceeded",
                    "retry_after": retry_after
                })
                response.status_code = 429
                response.headers['Retry-After'] = str(retry_after)
                return response

            return f(*args, **kwargs)
        return wrapped
    return decorator


def rate_limit_by_ip(requests_per_minute: int = 60):
    """Convenience decorator for simple per-IP rate limiting."""
    return rate_limit(requests_per_minute=requests_per_minute)
