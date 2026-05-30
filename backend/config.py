# -*- coding: utf-8 -*-
"""集中管理仿真魔法数与常量。

将散落在 core.py / api.py 的速率基准、带宽上限、调度阈值等以具名常量收敛于此，
便于统一调参与测试。数值与抽取前保持一致。

环境变量（全部以 SMARTNODE_ 为前缀）：
    SMARTNODE_HOST               : 监听地址，默认 127.0.0.1
    SMARTNODE_PORT               : 监听端口，默认 5000
    SMARTNODE_ENV                : 运行环境 development / production，默认 development
    SMARTNODE_TIME_SCALE         : 仿真时间倍率（正整数），默认 10
    SMARTNODE_LOG_LEVEL          : 日志级别 DEBUG/INFO/WARNING/ERROR，默认 INFO
    SMARTNODE_JWT_SECRET         : JWT 签名密钥（生产必填）
    SMARTNODE_API_KEY            : API 鉴权密钥（生产必填）
    SMARTNODE_CORS_ORIGINS       : 允许的 CORS 来源（逗号分隔），默认本机回环
    SMARTNODE_DEBUG_API          : 是否开启调试接口 0/1，默认 0
    SMARTNODE_SEED               : 随机种子，不填则非确定性
"""

import json
import logging
import os

# 仿真时钟（默认值；运行时通过 get_time_scale() 读取环境变量覆盖）
_DEFAULT_TIME_SCALE = 10

TIME_SCALE = _DEFAULT_TIME_SCALE  # 保持向后兼容的模块级常量，优先使用 get_time_scale()


def debug_api_enabled():
    """是否开启调试接口（默认关闭）。生产环境不暴露内部状态。"""
    return os.environ.get("SMARTNODE_DEBUG_API", "").strip().lower() in ("1", "true", "yes", "on")


# ==========================================
# 环境变量集中配置（敏感项一律来自环境，不入库）
# ==========================================
def is_production():
    return os.environ.get("SMARTNODE_ENV", "development").strip().lower() in ("prod", "production")


def get_jwt_secret():
    return os.environ.get("SMARTNODE_JWT_SECRET", "dev-insecure-secret-change-me")


def get_api_key():
    return os.environ.get("SMARTNODE_API_KEY")


def get_cors_origins():
    raw = os.environ.get("SMARTNODE_CORS_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000")
    return {o.strip() for o in raw.split(",") if o.strip()}


def get_bind_host():
    return os.environ.get("SMARTNODE_HOST", "127.0.0.1")


def get_seed():
    """从环境变量 SMARTNODE_SEED 读取随机种子（未设置返回 None=非确定性）。"""
    raw = os.environ.get("SMARTNODE_SEED")
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def get_bind_port():
    try:
        return int(os.environ.get("SMARTNODE_PORT", "5000"))
    except ValueError:
        return 5000


def get_time_scale() -> int:
    """从环境变量 SMARTNODE_TIME_SCALE 读取仿真时间倍率。

    未设置或值无效时回退到默认值 10（与历史行为一致）。
    建议范围：1（实时）~ 600（极速仿真）。
    """
    raw = os.environ.get("SMARTNODE_TIME_SCALE", "").strip()
    if raw:
        try:
            val = int(raw)
            if val > 0:
                return val
        except ValueError:
            pass
    return _DEFAULT_TIME_SCALE


def get_log_level() -> int:
    """从环境变量 SMARTNODE_LOG_LEVEL 或 LOG_LEVEL 解析日志级别。

    SMARTNODE_LOG_LEVEL 优先级高于 LOG_LEVEL（兼容旧约定）。
    默认返回 logging.INFO。
    """
    raw = (
        os.environ.get("SMARTNODE_LOG_LEVEL")
        or os.environ.get("LOG_LEVEL")
        or "INFO"
    ).upper().strip()
    return getattr(logging, raw, logging.INFO)


class LayeredSettings:
    """分层配置：默认 < 文件(JSON) < 环境变量 < 运行时覆盖。

    后加载的层覆盖先前层。环境变量键统一为 ``SMARTNODE_<UPPER_KEY>``。
    """

    DEFAULTS = {
        "env": "development",
        "host": "127.0.0.1",
        "port": 5000,
        "time_scale": _DEFAULT_TIME_SCALE,
        "log_level": "INFO",
        "cors_origins": "http://localhost:5000,http://127.0.0.1:5000",
        "debug_api": False,
        "background_task_enabled": False,
    }

    def __init__(self, config_file=None):
        self._values = dict(self.DEFAULTS)
        if config_file:
            self.load_file(config_file)
        self.load_env()
        self._runtime = {}

    def load_file(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                self._values.update(json.load(f) or {})
        except (OSError, ValueError):
            pass
        return self

    def load_env(self):
        for key in self._values:
            env_key = "SMARTNODE_" + key.upper()
            if env_key in os.environ:
                self._values[key] = _coerce(self._values[key], os.environ[env_key])
        return self

    def set(self, key, value):
        """运行时覆盖（最高优先级）。"""
        self._runtime[key] = value
        return self

    def get(self, key, default=None):
        if key in self._runtime:
            return self._runtime[key]
        return self._values.get(key, default)

    def as_dict(self):
        merged = dict(self._values)
        merged.update(self._runtime)
        return merged


def _coerce(template, raw):
    if isinstance(template, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(template, int):
        try:
            return int(raw)
        except ValueError:
            return template
    return raw


def validate_config():
    """启动时校验：生产模式下必须显式提供密钥，缺失即拒启。返回告警列表。"""
    problems = []
    if is_production():
        if get_jwt_secret() == "dev-insecure-secret-change-me":
            problems.append("SMARTNODE_JWT_SECRET 未设置（生产环境必须提供强随机密钥）")
        if not get_api_key():
            problems.append("SMARTNODE_API_KEY 未设置（生产环境必须开启鉴权）")
    if problems:
        raise RuntimeError("配置校验失败:\n  - " + "\n  - ".join(problems))
    return problems

# 资源带宽上限 (Mbps)
SATELLITE_MAX_BANDWIDTH = 600
GS_MAX_BANDWIDTH = 1000
DEFAULT_RELAY_BANDWIDTH = 2000

# 调度老化（饥饿规避）：有效优先级 = 基础优先级 + min(AGING_MAX, AGING_FACTOR * 等待秒数)
AGING_FACTOR = 0.02
AGING_MAX = 8.0

# 调度与切换阈值
RESOURCE_TIGHT_THRESHOLD = 0.95   # 平均利用率超过此值视为资源紧张
HANDOVER_RATE_RATIO = 1.2         # 链路切换：新速率需高于当前速率的倍数
HANDOVER_MIN_ELEVATION = 15       # 切换判定的最小仰角（防抖）
HANDOVER_MIN_DWELL = 5.0          # 切换前最小驻留时间（秒）
HANDOVER_COOLDOWN = 10.0          # 两次切换之间的冷却期（秒）

# 基础链路速率 (Mbps)
DIRECT_RATE_KA = 200
DIRECT_RATE_X = 100
RELAY_RATE_LEO_GEO = 500
RELAY_RATE_GEO_GS = 400
