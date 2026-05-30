# -*- coding: utf-8 -*-
"""确定性场景夹具 (Deterministic scenario fixtures).

本模块提供四类典型场景的夹具工厂函数，每个夹具均：
  - 固定 random.seed (通过 rng=random.Random(SEED))
  - 禁用后台仿真线程 (autostart=False)
  - 通过手动调用 _update_transmissions(delta) 推进仿真时间步

场景设计：
  1. task_cmd_immediate_accept  -- TASK_CMD 立即接受（指令类型跳过资源锁）
  2. raw_image_direct_only      -- RAW_IMAGE 仅直连（禁止中继）
  3. relay_bandwidth_exhausted  -- 中继带宽耗尽后低优先级被拒绝
  4. wait_timeout_scenario      -- 请求长期无链路触发 TIMEOUT_WAIT 拒绝

用法::

    from tests.fixtures.scenarios import build_task_cmd_engine, GOLDEN_SEED

    eng = build_task_cmd_engine()
    result = eng.submit_request({...})
"""

import random
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.core import (
    SimulationEngine,
    TransmissionRequest,
    DATA_TYPES,
    MAX_WAIT_LIMIT,
    REJECTION_REASONS,
)

# 固定种子：所有黄金快照均基于此种子生成，保证可复现
GOLDEN_SEED = 42

# 固定仿真参数
FIXED_GS_COUNT = 5   # 减小地面站数量加快测试
FIXED_LEO_COUNT = 4  # 减小卫星数量加快测试


def _make_seeded_engine(seed: int = GOLDEN_SEED) -> SimulationEngine:
    """创建固定种子、不启动后台线程的仿真引擎实例。"""
    rng = random.Random(seed)
    eng = SimulationEngine(
        ground_station_count=FIXED_GS_COUNT,
        leo_satellite_count=FIXED_LEO_COUNT,
        rng=rng,
        autostart=False,
    )
    eng.running = False
    # 重置请求ID计数器，保证每次运行的 REQ_ 编号一致
    TransmissionRequest._id_counter = 0
    return eng


def advance_engine(eng: SimulationEngine, total_seconds: float, step: float = 10.0) -> None:
    """手动步进引擎仿真时间（不依赖实时线程）。

    Args:
        eng: 仿真引擎实例（autostart=False）
        total_seconds: 要推进的总仿真时间（秒）
        step: 每步的时间增量（秒），默认 10 秒
    """
    elapsed = 0.0
    while elapsed < total_seconds:
        delta = min(step, total_seconds - elapsed)
        with eng.lock:
            eng.current_time += delta
            eng._update_resource_utilization()
            eng._update_decision_metrics()
            eng._update_transmissions(delta)
        elapsed += delta


def build_task_cmd_engine() -> SimulationEngine:
    """场景 1：TASK_CMD 立即接受场景引擎。

    TASK_CMD 属于 immediate=True 类型，_evaluate_request 会直接返回 (True, "指令类型立即接受")。
    本场景验证无需任何链路可见、立即进入 accepted 状态。
    """
    return _make_seeded_engine()


def build_raw_image_engine() -> SimulationEngine:
    """场景 2：RAW_IMAGE 仅直连场景引擎。

    RAW_IMAGE 的 allowed_links=["direct"]，中继路径必须被忽略。
    本场景验证提交后的 transmission_method 仅为 "direct" 或请求处于等待（无链路时）。
    """
    return _make_seeded_engine()


def build_relay_exhausted_engine() -> SimulationEngine:
    """场景 3：中继带宽耗尽场景引擎。

    预先手动填满 GEO 中继的带宽占用，使后续低优先级请求因 BANDWIDTH_EXCEEDED 被拒绝。
    """
    eng = _make_seeded_engine()
    # 通过直接操作资源占用模拟带宽耗尽
    for geo in eng.geo_relays:
        geo_id = geo["id"]
        max_bw = geo.get("bandwidth", 1600)
        # 在资源占用字典中填入虚拟请求，使带宽检查失败
        if geo_id not in eng.resource_usage["geo_relays"]:
            eng.resource_usage["geo_relays"][geo_id] = []
        # 填充满带宽占用：写入一个占满带宽的虚拟请求标识
        eng.resource_usage["geo_relays"][geo_id].append("DUMMY_BW_FILL")
        # 同步到 _resources 的 bandwidth_usage
        if hasattr(eng._resources, "_bandwidth_usage"):
            eng._resources._bandwidth_usage[geo_id] = max_bw
        elif hasattr(eng._resources, "bandwidth_usage"):
            eng._resources.bandwidth_usage[geo_id] = max_bw
    return eng


def build_timeout_engine() -> SimulationEngine:
    """场景 4：等待超时场景引擎。

    创建引擎后推进超过 max_delay 的时间，使 accepted 状态的请求触发 TIMEOUT_WAIT 拒绝。
    本场景通过极短的 max_delay 快速触发超时。
    """
    return _make_seeded_engine()


def extract_request_snapshot(req_dict: dict) -> dict:
    """从请求字典中提取黄金快照所需的字段子集（排除时间戳等易变字段）。

    Args:
        req_dict: TransmissionRequest.to_dict() 的返回值

    Returns:
        包含核心稳定字段的字典，用于黄金比对
    """
    return {
        "data_type": req_dict.get("data_type"),
        "status": req_dict.get("status"),
        "reject_reason": req_dict.get("reject_reason"),
        "transmission_method": req_dict.get("transmission_method"),
        "source": req_dict.get("source"),
    }


def extract_stats_snapshot(stats: dict) -> dict:
    """从引擎统计中提取黄金快照所需的计数字段（排除浮点利用率等非确定字段）。

    Args:
        stats: engine.stats 字典

    Returns:
        包含请求计数的稳定字典，用于黄金比对
    """
    return {
        "total_requests": stats.get("total_requests", 0),
        "accepted_requests": stats.get("accepted_requests", 0),
        "rejected_requests": stats.get("rejected_requests", 0),
    }
