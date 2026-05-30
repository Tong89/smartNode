# -*- coding: utf-8 -*-
"""
结构化日志配置模块

提供基于 structlog 的 JSON/控制台双渲染器，支持环境变量配置。

环境变量:
    LOG_LEVEL  : 日志级别 (DEBUG / INFO / WARNING / ERROR / CRITICAL)，默认 INFO
    LOG_FORMAT : 输出格式 (json / console)，默认 console

遥测级别映射 (与原 _log() 保持一致):
    high   -> logging.WARNING  （高优先级事件，始终输出）
    normal -> logging.INFO     （常规信息）
    low    -> logging.DEBUG    （调试详情，默认过滤）
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

try:
    import structlog
    _HAS_STRUCTLOG = True
except ImportError:  # pragma: no cover — 仅在依赖缺失时降级
    _HAS_STRUCTLOG = False

# ---------------------------------------------------------------------------
# 遥测级别 -> Python 日志级别映射
# ---------------------------------------------------------------------------
TELEMETRY_LEVEL_MAP: dict[str, int] = {
    "high": logging.WARNING,
    "normal": logging.INFO,
    "low": logging.DEBUG,
}

# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

def _resolve_log_level() -> int:
    """从环境变量 LOG_LEVEL 解析日志级别，默认 INFO。"""
    raw = os.environ.get("LOG_LEVEL", "INFO").upper()
    return getattr(logging, raw, logging.INFO)


def _resolve_log_format() -> str:
    """从环境变量 LOG_FORMAT 解析输出格式，默认 console。"""
    return os.environ.get("LOG_FORMAT", "console").lower()


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------

def configure_logging() -> None:
    """
    配置 structlog 与标准库 logging。

    调用一次即可；重复调用幂等（structlog.configure 可安全重入）。
    """
    level = _resolve_log_level()
    fmt = _resolve_log_format()

    # 配置根 logger
    logging.basicConfig(
        level=level,
        stream=sys.stdout,
        format="%(message)s",
    )
    # 将 structlog 以外的库（Flask/werkzeug 等）日志级别对齐
    logging.getLogger("werkzeug").setLevel(max(level, logging.WARNING))

    if not _HAS_STRUCTLOG:
        return

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=False),
        structlog.processors.StackInfoRenderer(),
    ]

    if fmt == "json":
        # JSON 渲染器：适合生产/容器环境日志聚合
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # 带颜色控制台渲染器：适合本地开发
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty() or sys.stdout.isatty()),
        ]

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "smartnode") -> Any:
    """
    返回已绑定名称的结构化 logger。

    若 structlog 不可用，回退到标准库 Logger。
    """
    if _HAS_STRUCTLOG:
        return structlog.get_logger(name)
    return logging.getLogger(name)


def telemetry_level_to_log_level(telemetry_level: str) -> int:
    """将遥测级别字符串转换为 Python logging 级别整数。"""
    return TELEMETRY_LEVEL_MAP.get(telemetry_level, logging.INFO)
