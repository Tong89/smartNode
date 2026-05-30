# -*- coding: utf-8 -*-
"""RBAC 角色模型与接口授权。

三角色权限递增：viewer（只读） < operator（可提交请求） < admin（可改系统配置）。
``require_role`` 装饰器基于 before_request 注入的 ``g.identity.role`` 做最小权限校验。
"""
from functools import wraps

from flask import g

from backend.errors import error_response

ROLE_LEVELS = {"viewer": 1, "operator": 2, "admin": 3}


def current_role():
    ident = getattr(g, "identity", {}) or {}
    return ident.get("role", "viewer")


def require_role(min_role):
    """要求当前身份角色不低于 min_role，否则返回 403。"""
    required = ROLE_LEVELS.get(min_role, 99)

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if ROLE_LEVELS.get(current_role(), 0) < required:
                return error_response("FORBIDDEN")
            return fn(*args, **kwargs)

        return wrapper

    return decorator
