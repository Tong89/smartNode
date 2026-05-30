# -*- coding: utf-8 -*-
"""场景管理模块：定义 Scenario 数据模型，提供场景的保存、加载、JSON/YAML 导入导出。

功能：
- load_scenario : 从 JSON 文件加载场景资源定义（原有功能）
- ScenarioManager : 场景对象管理器
  * save(engine) -> dict          将引擎当前状态序列化为场景字典
  * load(engine, data)            从场景字典恢复引擎资源配置
  * to_json(data) -> str          序列化为 JSON 字符串
  * from_json(text) -> dict       从 JSON 字符串反序列化
  * to_yaml(data) -> str          序列化为 YAML 字符串（依赖 PyYAML；不可用时回退 JSON）
  * from_yaml(text) -> dict       从 YAML 字符串反序列化
  * validate(data) -> list[str]   校验场景字典，返回错误列表（空列表表示合法）

场景字典结构（Scenario Schema）：
{
  "version": "1",
  "name": str,           # 场景名称（可选）
  "saved_at": str,       # ISO-8601 时间戳
  "ground_station_count": int,
  "leo_satellite_count": int,
  "geo_relay_count": int,
  "data_types": [...],   # 当前激活的数据类型键列表
}
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.orbit import OrbitalElements

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DEFAULT_SCENARIO = os.path.join(DATA_DIR, "scenario.default.json")

# YAML 是可选依赖；缺失时相关方法回退到 JSON
try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
except ImportError:
    _yaml = None  # type: ignore[assignment]
    _YAML_AVAILABLE = False

SCENARIO_VERSION = "1"

# ── 原有加载函数（保持向后兼容）────────────────────────────────────────────


def load_scenario(path: Optional[str] = None) -> Dict[str, Any]:
    """加载场景资源定义，返回 dict(ground_stations, leo_satellites, geo_relays, data_types)。

    leo_satellites 还原为 OrbitalElements 对象；其余保持 dict 结构以兼容现有引擎。
    """
    path = path or DEFAULT_SCENARIO
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    leo = [
        OrbitalElements(
            name=s["name"],
            sat_id=s["sat_id"],
            semi_major_axis=s["a"],
            eccentricity=s["e"],
            inclination=s["i"],
            raan=s["raan"],
            arg_perigee=s["omega"],
            mean_anomaly=s["M0"],
        )
        for s in raw.get("leo_satellites", [])
    ]

    data_types: Dict[str, Any] = {}
    for k, v in raw.get("data_types", {}).items():
        cfg = dict(v)
        if "size_range" in cfg and isinstance(cfg["size_range"], list):
            cfg["size_range"] = tuple(cfg["size_range"])
        if "priority_range" in cfg and isinstance(cfg["priority_range"], list):
            cfg["priority_range"] = tuple(cfg["priority_range"])
        data_types[k] = cfg

    return {
        "ground_stations": raw.get("ground_stations", []),
        "leo_satellites": leo,
        "geo_relays": raw.get("geo_relays", []),
        "data_types": data_types,
    }


# ── 场景管理器 ────────────────────────────────────────────────────────────────


class ScenarioManager:
    """序列化当前仿真资源配置为可保存的场景对象，并支持从场景还原。

    ``save`` / ``load`` 操作仅操作资源数量配置（地面站、LEO 卫星），
    不保存正在进行中的传输请求或实时仿真状态（快照功能由独立的 snapshot 模块负责）。
    """

    @staticmethod
    def save(engine: Any, name: str = "") -> Dict[str, Any]:
        """将引擎当前资源配置序列化为场景字典。

        Parameters
        ----------
        engine:
            ``SimulationEngine`` 实例。
        name:
            场景名称（可选，便于人类识别）。

        Returns
        -------
        dict
            符合 Scenario Schema 的字典，可直接序列化为 JSON 或 YAML。
        """
        return {
            "version": SCENARIO_VERSION,
            "name": name or "unnamed",
            "saved_at": datetime.now(tz=timezone.utc).isoformat(),
            "ground_station_count": len(engine.ground_stations),
            "leo_satellite_count": len(engine.leo_satellites),
            "geo_relay_count": len(engine.geo_relays),
            "data_types": list(engine.DATA_TYPES.keys()) if hasattr(engine, "DATA_TYPES") else [],
        }

    @staticmethod
    def load(engine: Any, data: Dict[str, Any]) -> Dict[str, Any]:
        """从场景字典恢复引擎资源配置。

        只恢复可在运行时动态调整的资源数量（地面站、LEO 卫星）。

        Parameters
        ----------
        engine:
            ``SimulationEngine`` 实例。
        data:
            符合 Scenario Schema 的字典（由 :meth:`save` 生成或导入）。

        Returns
        -------
        dict
            包含恢复结果摘要的字典。
        """
        errors = ScenarioManager.validate(data)
        if errors:
            raise ValueError("场景数据非法: " + "; ".join(errors))

        changes: List[str] = []

        gs_count = data.get("ground_station_count")
        if gs_count is not None and isinstance(gs_count, int):
            current_gs = len(engine.ground_stations)
            if gs_count != current_gs:
                engine.update_ground_station_count(gs_count)
                changes.append(f"地面站: {current_gs} → {gs_count}")

        leo_count = data.get("leo_satellite_count")
        if leo_count is not None and isinstance(leo_count, int):
            current_leo = len(engine.leo_satellites)
            if leo_count != current_leo:
                engine.update_leo_satellite_count(leo_count)
                changes.append(f"LEO卫星: {current_leo} → {leo_count}")

        return {
            "restored": True,
            "scenario_name": data.get("name", ""),
            "saved_at": data.get("saved_at", ""),
            "changes": changes,
            "ground_station_count": len(engine.ground_stations),
            "leo_satellite_count": len(engine.leo_satellites),
        }

    @staticmethod
    def validate(data: Any) -> List[str]:
        """校验场景字典的结构合法性。

        Parameters
        ----------
        data:
            待校验的对象。

        Returns
        -------
        list[str]
            错误描述列表；空列表表示合法。
        """
        errors: List[str] = []
        if not isinstance(data, dict):
            return ["顶层结构必须为对象（dict）"]

        version = data.get("version")
        if version is None:
            errors.append("缺少 'version' 字段")
        elif str(version) != SCENARIO_VERSION:
            errors.append(f"版本不兼容: 期望 '{SCENARIO_VERSION}'，收到 '{version}'")

        for field, expected_type in [
            ("ground_station_count", int),
            ("leo_satellite_count", int),
        ]:
            val = data.get(field)
            if val is None:
                errors.append(f"缺少必填字段 '{field}'")
            elif not isinstance(val, int) or val < 0:
                errors.append(f"字段 '{field}' 必须为非负整数，收到: {val!r}")

        return errors

    # ── 序列化辅助 ──────────────────────────────────────────────────────────

    @staticmethod
    def to_json(data: Dict[str, Any], *, indent: int = 2) -> str:
        """将场景字典序列化为 JSON 字符串。"""
        return json.dumps(data, ensure_ascii=False, indent=indent)

    @staticmethod
    def from_json(text: str) -> Dict[str, Any]:
        """从 JSON 字符串反序列化场景字典。"""
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON 解析失败: {exc}") from exc
        if not isinstance(obj, dict):
            raise ValueError("JSON 根对象必须为 object")
        return obj

    @staticmethod
    def to_yaml(data: Dict[str, Any]) -> str:
        """将场景字典序列化为 YAML 字符串。

        若 PyYAML 不可用，退回 JSON（并附带注释说明）。
        """
        if _YAML_AVAILABLE:
            return _yaml.dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
        # 优雅降级
        return "# PyYAML 不可用，以下为 JSON 格式\n" + ScenarioManager.to_json(data)

    @staticmethod
    def from_yaml(text: str) -> Dict[str, Any]:
        """从 YAML（或 JSON）字符串反序列化场景字典。

        YAML 是 JSON 的超集，因此可接受纯 JSON 输入。
        若 PyYAML 不可用则自动尝试 JSON 解析。
        """
        if _YAML_AVAILABLE:
            try:
                obj = _yaml.safe_load(text)
            except _yaml.YAMLError as exc:
                raise ValueError(f"YAML 解析失败: {exc}") from exc
        else:
            try:
                obj = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON/YAML 解析失败（PyYAML 不可用）: {exc}") from exc

        if not isinstance(obj, dict):
            raise ValueError("YAML 根对象必须为 mapping")
        return obj
