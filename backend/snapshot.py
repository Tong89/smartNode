# -*- coding: utf-8 -*-
"""仿真快照模块：将运行中的仿真状态序列化为可保存的快照，并支持从快照恢复。

快照包含以下状态：
- current_time       : 仿真时钟（秒）
- transmission_requests : 进行中的请求列表（序列化为 dict）
- request_history    : 已完成/拒绝的历史请求列表（序列化为 dict）
- resource_usage     : 卫星/地面站/中继的占用状态
- resource_time_pool : 时间槽预约池
- stats              : 统计计数器与决策指标
- replay_mode        : 是否处于回放模式（回放模式下主循环暂停）
- id_counter         : TransmissionRequest._id_counter，用于恢复后 ID 连续

快照字典结构（Snapshot Schema v1）：
{
  "version": "1",
  "saved_at": str,         # ISO-8601 时间戳
  "label": str,            # 快照标签（可选，人类可读）
  "current_time": float,   # 仿真时钟
  "id_counter": int,       # 请求 ID 计数器
  "transmission_requests": [...],  # 进行中请求
  "request_history": [...],        # 历史请求
  "resource_usage": {
    "satellites": {...},
    "ground_stations": {...},
    "geo_relays": {...},
  },
  "resource_time_pool": {...},
  "stats": {...},
}
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

SNAPSHOT_VERSION = "1"


class SnapshotManager:
    """仿真快照管理器。

    提供静态方法，无需实例化即可使用。

    Methods
    -------
    take(engine, label) -> dict
        对引擎当前状态拍快照，返回快照字典。
    restore(engine, snapshot)
        将引擎状态回滚到快照时刻，同时挂起/恢复主循环。
    validate(snapshot) -> list[str]
        校验快照字典结构，返回错误列表（空 = 合法）。
    to_json(snapshot) -> str
        序列化快照为 JSON 字符串。
    from_json(text) -> dict
        从 JSON 字符串反序列化快照字典。
    """

    # ── 拍快照 ─────────────────────────────────────────────────────────────────

    @staticmethod
    def take(engine: Any, label: str = "") -> Dict[str, Any]:
        """对仿真引擎当前状态拍快照。

        Parameters
        ----------
        engine:
            ``SimulationEngine`` 实例。
        label:
            可选的快照标签，便于人类识别（例如场景名称或事件描述）。

        Returns
        -------
        dict
            快照字典，包含 current_time、请求列表、资源占用与统计数据。
        """
        from backend.core import TransmissionRequest  # 避免循环导入

        with engine.lock:
            # 序列化进行中的请求
            active_requests = [req.to_dict() for req in engine.transmission_requests]
            # 序列化历史请求
            history_requests = [req.to_dict() for req in engine.request_history]

            # 深拷贝资源占用状态（嵌套容器）
            resource_usage = copy.deepcopy(dict(engine.resource_usage))
            resource_time_pool = copy.deepcopy(dict(engine._resources.time_pool))

            # 深拷贝统计数据
            stats = copy.deepcopy(engine.stats)

            snapshot = {
                "version": SNAPSHOT_VERSION,
                "saved_at": datetime.now(tz=timezone.utc).isoformat(),
                "label": label or "",
                "current_time": engine.current_time,
                "id_counter": TransmissionRequest._id_counter,
                "transmission_requests": active_requests,
                "request_history": history_requests,
                "resource_usage": resource_usage,
                "resource_time_pool": resource_time_pool,
                "stats": stats,
            }

        return snapshot

    # ── 从快照恢复 ──────────────────────────────────────────────────────────────

    @staticmethod
    def restore(engine: Any, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        """将引擎状态回滚到快照时刻。

        恢复后引擎进入 **回放模式**：主仿真循环暂停（``running=False``），
        /api/data 返回快照时刻的态势数据，直到调用方显式调用
        ``engine.start_simulation()`` 或 ``engine.resume_from_snapshot()`` 重启。

        Parameters
        ----------
        engine:
            ``SimulationEngine`` 实例。
        snapshot:
            由 :meth:`take` 生成的快照字典。

        Returns
        -------
        dict
            恢复摘要，包含 restored_time、request_count、history_count。

        Raises
        ------
        ValueError
            快照结构非法或版本不兼容时抛出。
        """
        errors = SnapshotManager.validate(snapshot)
        if errors:
            raise ValueError("快照数据非法: " + "; ".join(errors))

        from backend.core import TransmissionRequest  # 避免循环导入

        with engine.lock:
            # 1. 暂停主循环（回放模式）
            engine.running = False

            # 2. 恢复仿真时钟
            engine.current_time = float(snapshot["current_time"])

            # 3. 恢复 ID 计数器（保持唯一性）
            TransmissionRequest._id_counter = int(snapshot.get("id_counter", 0))

            # 4. 重建请求对象：从 dict 还原 TransmissionRequest
            engine.transmission_requests = SnapshotManager._rebuild_requests(
                snapshot.get("transmission_requests", [])
            )
            engine.request_history = SnapshotManager._rebuild_requests(
                snapshot.get("request_history", [])
            )

            # 5. 恢复资源占用状态
            raw_usage = snapshot.get("resource_usage", {})
            engine._resources.usage["satellites"] = {
                k: list(v) for k, v in raw_usage.get("satellites", {}).items()
            }
            engine._resources.usage["ground_stations"] = {
                k: list(v) for k, v in raw_usage.get("ground_stations", {}).items()
            }
            engine._resources.usage["geo_relays"] = {
                k: list(v) for k, v in raw_usage.get("geo_relays", {}).items()
            }

            # 6. 恢复时间槽预约池
            engine._resources.time_pool = copy.deepcopy(snapshot.get("resource_time_pool", {}))

            # 7. 恢复统计数据
            engine.stats.update(copy.deepcopy(snapshot.get("stats", {})))

            # 8. 标记为回放模式
            engine._replay_mode = True
            engine._replay_snapshot = snapshot

        return {
            "restored": True,
            "replay_mode": True,
            "restored_time": engine.current_time,
            "label": snapshot.get("label", ""),
            "saved_at": snapshot.get("saved_at", ""),
            "request_count": len(engine.transmission_requests),
            "history_count": len(engine.request_history),
        }

    # ── 辅助：从 dict 重建 TransmissionRequest ─────────────────────────────────

    @staticmethod
    def _rebuild_requests(req_dicts: List[Dict[str, Any]]) -> List[Any]:
        """将 to_dict() 序列化的请求列表还原为 TransmissionRequest 实例。

        注意：不调用 __init__，而是直接构造最小实例再按字段赋值，
        以避免触发 ID 自增、副作用初始化等逻辑。
        """
        from backend.core import TransmissionRequest  # 避免循环导入

        result = []
        for d in req_dicts:
            # 使用合法参数构造实例（会自增 _id_counter，稍后被 restore 覆盖）
            req = TransmissionRequest(
                data_type=d.get("data_type", "DATA_SLICE"),
                data_size=d.get("data_size", 0),
                priority=d.get("priority", 1),
                max_delay=d.get("max_delay", 1800),
                start_time=d.get("start_time"),
                end_time=d.get("end_time"),
                satellite_id=d.get("satellite_id"),
                source=d.get("source", "user"),
                experiment_requirements=d.get("experiment_requirements", {}),
                selected_ground_stations=d.get("selected_ground_stations", []),
            )
            # 覆盖 ID 为快照中的原始值
            req.id = d.get("id", req.id)

            # 恢复状态字段
            req.status = d.get("status", "pending")
            req.reject_reason = d.get("reject_reason")
            req.assigned_link = d.get("assigned_link")
            req.submit_time = d.get("submit_time")
            req.start_transmit_time = d.get("start_transmit_time")
            req.complete_time = d.get("complete_time")
            req.progress = d.get("progress", 0.0)
            req.transmission_rate = d.get("transmission_rate", 0.0)
            req.selected_ground_station = d.get("selected_ground_station")
            req.selected_relay = d.get("selected_relay")
            req.selected_relay2 = d.get("selected_relay2")
            req.transmission_method = d.get("transmission_method")
            req.predicted_pass_time = d.get("predicted_pass_time")
            req.wait_time = d.get("wait_time", 0.0)
            req.transmission_time = d.get("transmission_time", 0.0)
            result.append(req)
        return result

    # ── 校验 ──────────────────────────────────────────────────────────────────

    @staticmethod
    def validate(snapshot: Any) -> List[str]:
        """校验快照字典的结构合法性。

        Returns
        -------
        list[str]
            错误列表；空列表表示快照合法。
        """
        errors: List[str] = []
        if not isinstance(snapshot, dict):
            return ["快照顶层结构必须为对象（dict）"]

        version = snapshot.get("version")
        if version is None:
            errors.append("缺少 'version' 字段")
        elif str(version) != SNAPSHOT_VERSION:
            errors.append(f"版本不兼容: 期望 '{SNAPSHOT_VERSION}'，收到 '{version}'")

        if "current_time" not in snapshot:
            errors.append("缺少必填字段 'current_time'")
        elif not isinstance(snapshot["current_time"], (int, float)):
            errors.append("字段 'current_time' 必须为数值")

        if "id_counter" in snapshot and not isinstance(snapshot["id_counter"], int):
            errors.append("字段 'id_counter' 必须为整数")

        for field in ("transmission_requests", "request_history"):
            val = snapshot.get(field)
            if val is not None and not isinstance(val, list):
                errors.append(f"字段 '{field}' 必须为列表")

        return errors

    # ── 序列化辅助 ────────────────────────────────────────────────────────���───

    @staticmethod
    def to_json(snapshot: Dict[str, Any], *, indent: int = 2) -> str:
        """将快照字典序列化为 JSON 字符串。"""
        return json.dumps(snapshot, ensure_ascii=False, indent=indent)

    @staticmethod
    def from_json(text: str) -> Dict[str, Any]:
        """从 JSON 字符串反序列化快照字典。

        Raises
        ------
        ValueError
            JSON 解析失败或根对象非 dict 时抛出。
        """
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"快照 JSON 解析失败: {exc}") from exc
        if not isinstance(obj, dict):
            raise ValueError("快照 JSON 根对象必须为 object")
        return obj
