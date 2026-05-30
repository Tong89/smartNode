# -*- coding: utf-8 -*-
"""统一响应包络。

成功：``{"code": 0, "data": ..., "meta": ..., "request_id": ...}``
失败：复用 errors.error_response 的 ``{"status":"error","code","message","request_id"}``。

客户端（frontend/app.js fetchJson）会对 ``code === 0`` 的包络透明解包为 ``data``，因此后端可渐进采用。
"""
import uuid

from flask import jsonify

from backend.errors import error_response

# 错误码枚举（与 errors.ERROR_CODES 对齐）
ERROR_CODE = {
    "OK": 0,
    "BAD_REQUEST": "BAD_REQUEST",
    "VALIDATION_FAILED": "VALIDATION_ERROR",
    "UNAUTHORIZED": "UNAUTHORIZED",
    "FORBIDDEN": "FORBIDDEN",
    "RESOURCE_NOT_FOUND": "NOT_FOUND",
    "RATE_LIMITED": "RATE_LIMITED",
    "INTERNAL_ERROR": "INTERNAL_ERROR",
}


def ok(data=None, meta=None):
    body = {
        "code": 0,
        "data": data,
        "request_id": uuid.uuid4().hex[:12],
    }
    if meta is not None:
        body["meta"] = meta
    return jsonify(body)


def err(code, message=None, http_status=None, details=None):
    return error_response(code, message=message, status=http_status, details=details)
