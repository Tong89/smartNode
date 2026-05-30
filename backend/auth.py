# -*- coding: utf-8 -*-
"""可插拔认证中间件 —— API Key 鉴权基线。

通过 Flask before_request 统一校验 ``Authorization: Bearer <key>`` 或 ``X-API-Key`` 头。
密钥来自环境变量 ``SMARTNODE_API_KEY``；为兼容本地/开源开放部署，未配置密钥时降级为开放模式
（记录告警）。健康检查与静态资源匿名放行。为后续 JWT 会话与 RBAC 提供统一鉴权入口。
"""
import logging
import os
import time
from functools import wraps

import jwt
from flask import g, request

from backend.errors import error_response

logger = logging.getLogger("smartnode")

JWT_ALGORITHM = "HS256"
ACCESS_TTL = 3600        # access token 1 小时
REFRESH_TTL = 7 * 86400  # refresh token 7 天

# 演示用户库（生产应替换为真实用户存储/目录服务）
DEMO_USERS = {
    "admin": {"password": "admin123", "role": "admin"},
    "operator": {"password": "operator123", "role": "operator"},
    "viewer": {"password": "viewer123", "role": "viewer"},
}


def jwt_secret():
    return os.environ.get("SMARTNODE_JWT_SECRET", "dev-insecure-secret-change-me")


def authenticate_user(username, password):
    user = DEMO_USERS.get(username)
    if user and password is not None and user["password"] == password:
        return user["role"]
    return None


def create_token(sub, role, token_type, ttl):
    now = int(time.time())
    payload = {"sub": sub, "role": role, "type": token_type, "iat": now, "exp": now + ttl}
    return jwt.encode(payload, jwt_secret(), algorithm=JWT_ALGORITHM)


def create_access_token(sub, role):
    return create_token(sub, role, "access", ACCESS_TTL)


def create_refresh_token(sub, role):
    return create_token(sub, role, "refresh", REFRESH_TTL)


def decode_token(token):
    """解码并校验 JWT（过期/篡改会抛出异常）。"""
    return jwt.decode(token, jwt_secret(), algorithms=[JWT_ALGORITHM])

# 匿名可访问的精确路径与前缀白名单
PUBLIC_PATHS = {"/", "/api/health", "/favicon.ico", "/api/auth/login", "/api/auth/refresh"}
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

        # 1) 显式提供了 Bearer 凭证：必须有效（JWT 或承载的 API Key），否则一律 401（含篡改/过期）
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[len("Bearer "):].strip()
            try:
                claims = decode_token(token)
                if claims.get("type") == "access":
                    g.identity = {
                        "auth": "jwt",
                        "sub": claims.get("sub"),
                        "role": claims.get("role", "viewer"),
                    }
                    return None
            except jwt.PyJWTError:
                pass
            if configured and token == configured:
                g.identity = {"auth": "api_key", "role": "admin"}
                return None
            # Bearer 提供了但无效，不再降级开放
            return error_response("UNAUTHORIZED")

        # 2) X-API-Key / 开放模式
        if not configured:
            g.identity = {"auth": "open", "role": "admin"}
            return None

        provided = request.headers.get("X-API-Key")
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
