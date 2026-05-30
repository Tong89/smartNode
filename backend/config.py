# -*- coding: utf-8 -*-
"""集中管理仿真魔法数与常量。

将散落在 core.py / api.py 的速率基准、带宽上限、调度阈值等以具名常量收敛于此，
便于统一调参与测试。数值与抽取前保持一致。
"""

import json
import os

# 仿真时钟
TIME_SCALE = 10  # 仿真加速倍率


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


def get_bind_port():
    try:
        return int(os.environ.get("SMARTNODE_PORT", "5000"))
    except ValueError:
        return 5000


class LayeredSettings:
    """分层配置：默认 < 文件(JSON) < 环境变量 < 运行时覆盖。

    后加载的层覆盖先前层。环境变量键统一为 ``SMARTNODE_<UPPER_KEY>``。
    """

    DEFAULTS = {
        "env": "development",
        "host": "127.0.0.1",
        "port": 5000,
        "time_scale": TIME_SCALE,
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
