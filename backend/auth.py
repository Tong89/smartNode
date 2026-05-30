# -*- coding: utf-8 -*-
"""可插拔认证中间件 —— API Key 鉴权基线。

通过 Flask before_request 统一校验 ``Authorization: Bearer <key>`` 或 ``X-API-Key`` 头。
密钥来自环境变量 ``SMARTNODE_API_KEY``；为兼容本地/开源开放部署，未配置密钥时降级为开放模式
（记录告警）。健康检查与静态资源匿名放行。为后续 JWT 会话与 RBAC 提供统一鉴权入口。
"""
import logging
import os
from functools import wraps

from flask import g, request

from backend.errors import error_response

logger = logging.getLogger("smartnode")

# 匿名可访问的精确路径与前缀白名单
PUBLIC_PATHS = {"/", "/api/health", "/favicon.ico"}
PUBLIC_PREFIXES = ("/frontend", "/static")


def configured_api_key():
    return os.environ.get("SMARTNODE_API_KEY")


def _extract_key():
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer "):].strip()
    return request.headers.get("X-API-Key")


def is_public_path(path):
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


def init_auth(app):
    """注册全局鉴权钩子。"""

    @app.before_request
    def _authenticate():  # noqa: ANN202
        if request.method == "OPTIONS":
            return None  # CORS 预检放行
        path = request.path
        if is_public_path(path) or not path.startswith("/api/"):
            return None

        configured = configured_api_key()
        if not configured:
            # 未配置密钥 -> 开放模式（可插拔），便于本地/开源演示
            g.identity = {"auth": "open", "role": "admin"}
            return None

        provided = _extract_key()
        if not provided or provided != configured:
            return error_response("UNAUTHORIZED")

        g.identity = {"auth": "api_key", "role": "admin"}
        return None


def require_auth(fn):
    """显式标注需要鉴权的路由（实际校验由 before_request 统一完成）。"""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    return wrapper
