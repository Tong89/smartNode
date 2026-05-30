# -*- coding: utf-8 -*-
"""轻量接口限流（内置滑动窗口，零外部依赖）。

按身份（JWT sub / API Key）优先、回退到客户端 IP 做窗口限速；写接口配额更严格。
超限返回 429 + Retry-After，并暴露剩余配额响应头。
"""
import threading
import time
from functools import wraps

from flask import g, request

from backend.errors import error_response


class SlidingWindowLimiter:
    def __init__(self):
        self._hits = {}
        self._lock = threading.Lock()

    def check(self, key, limit, window):
        """返回 (allowed, remaining, retry_after_seconds)。"""
        now = time.time()
        cutoff = now - window
        with self._lock:
            q = self._hits.setdefault(key, [])
            while q and q[0] < cutoff:
                q.pop(0)
            if len(q) >= limit:
                retry = window - (now - q[0])
                return False, 0, max(0.0, retry)
            q.append(now)
            return True, limit - len(q), 0.0


_limiter = SlidingWindowLimiter()


def _identity_key():
    ident = getattr(g, "identity", {}) or {}
    sub = ident.get("sub")
    if sub:
        return f"id:{sub}"
    if ident.get("auth") == "api_key":
        return "id:api_key"
    return f"ip:{request.remote_addr or 'unknown'}"


def rate_limit(limit, window=60):
    """对被装饰路由按 limit/window 限速（优先按身份，回退 IP）。"""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = f"{fn.__name__}:{_identity_key()}"
            allowed, remaining, retry = _limiter.check(key, limit, window)
            if not allowed:
                resp, status = error_response("RATE_LIMITED")
                resp.headers["Retry-After"] = str(int(retry) + 1)
                resp.headers["X-RateLimit-Limit"] = str(limit)
                resp.headers["X-RateLimit-Remaining"] = "0"
                return resp, status
            result = fn(*args, **kwargs)
            return result

        return wrapper

    return decorator
