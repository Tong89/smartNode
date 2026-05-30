# -*- coding: utf-8 -*-
"""统一错误响应与错误码体系（脱敏）。

向客户端只返回稳定错误码与中性消息，**绝不**回传 traceback / 文件路径 / 栈帧；
真实异常仅记录到服务端日志。为后续认证/限流/校验提供统一的错误结构。
"""
import logging
import uuid

from flask import jsonify

logger = logging.getLogger("smartnode")

# code -> (http_status, 默认中性消息)
ERROR_CODES = {
    "BAD_REQUEST": (400, "请求无效"),
    "VALIDATION_ERROR": (400, "请求参数校验失败"),
    "UNAUTHORIZED": (401, "未认证或令牌无效"),
    "FORBIDDEN": (403, "无权限执行该操作"),
    "NOT_FOUND": (404, "资源不存在"),
    "PAYLOAD_TOO_LARGE": (413, "请求体过大"),
    "UNSUPPORTED_MEDIA_TYPE": (415, "请求 Content-Type 不受支持"),
    "RATE_LIMITED": (429, "请求过于频繁，请稍后重试"),
    "INTERNAL_ERROR": (500, "服务内部错误"),
}


def error_response(code, message=None, status=None, details=None):
    """构造脱敏的统一错误响应 (body, http_status)。"""
    default_status, default_msg = ERROR_CODES.get(code, (500, "服务内部错误"))
    body = {
        "status": "error",
        "code": code,
        "message": message or default_msg,
        "request_id": uuid.uuid4().hex[:12],  # 便于把客户端报错关联到服务端日志
    }
    if details is not None:
        body["details"] = details
    return jsonify(body), (status or default_status)


def register_error_handlers(app):
    """注册兜底错误处理器，保证 4xx/5xx 都返回脱敏结构。"""

    @app.errorhandler(400)
    def _handle_400(e):  # noqa: ANN001
        return error_response("BAD_REQUEST")

    @app.errorhandler(404)
    def _handle_404(e):  # noqa: ANN001
        return error_response("NOT_FOUND")

    @app.errorhandler(413)
    def _handle_413(e):  # noqa: ANN001
        return error_response("PAYLOAD_TOO_LARGE")

    @app.errorhandler(415)
    def _handle_415(e):  # noqa: ANN001
        return error_response("UNSUPPORTED_MEDIA_TYPE")

    @app.errorhandler(429)
    def _handle_429(e):  # noqa: ANN001
        return error_response("RATE_LIMITED")

    @app.errorhandler(500)
    def _handle_500(e):  # noqa: ANN001
        logger.exception("Unhandled 500 error")
        return error_response("INTERNAL_ERROR")

    @app.errorhandler(Exception)
    def _handle_exception(e):  # noqa: ANN001
        # 记录真实异常到服务端日志，响应体保持脱敏
        logger.exception("Unhandled exception: %s", e)
        return error_response("INTERNAL_ERROR")
