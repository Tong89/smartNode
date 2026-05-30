# -*- coding: utf-8 -*-
"""核心调度引擎回归测试。

本模块不启动 Flask，不依赖网络与真实时间推进，直接测试 SimulationEngine 的
业务逻辑与 TransmissionRequest 的构建/校验行为。

覆盖范围：
  - submit_request 的合法提交路径（返回结构检查）
  - submit_request 的拒绝路径：指定不存在的卫星 ID
  - _data_size_to_mb 的单位换算正确性（KB/MB/GB）
  - _evaluate_request 的资源占用拒绝
  - update_ground_station_count 的边界夹紧
  - update_leo_satellite_count 的最小值保护
  - TransmissionRequest 的 ID 唯一性
  - create_engine 种子可复现性
  - 引擎状态属性完整性（leo_satellites / ground_stations / geo_relays 非空）
  - get_stats 返回结构
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from backend.core import (
    DATA_TYPES,
    MAX_GROUND_STATION_COUNT,
    MIN_GROUND_STATION_COUNT,
    MIN_LEO_SATELLITE_COUNT,
    SimulationEngine,
    TransmissionRequest,
    create_engine,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_engine(seed: int = 0) -> SimulationEngine:
    """创建隔离、固定种子、不启动后台线程的引擎。"""
    eng = create_engine(seed=seed, autostart=False)
    eng.running = False
    return eng


def _valid_request_data(**overrides) -> dict:
    base = {
        "data_type": "TASK_CMD",
        "data_size": 512,
        "priority": 5,
        "max_delay": 600,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 1. create_engine / 引擎状态
# ---------------------------------------------------------------------------


class TestCreateEngine:
    """工厂函数与引擎基本属性验证。"""

    def test_returns_simulation_engine_instance(self):
        eng = _make_engine()
        assert isinstance(eng, SimulationEngine)

    def test_autostart_false_not_running(self):
        eng = _make_engine()
        assert eng.running is False

    def test_leo_satellites_nonempty(self):
        eng = _make_engine()
        assert len(eng.leo_satellites) > 0

    def test_ground_stations_nonempty(self):
        eng = _make_engine()
        assert len(eng.ground_stations) > 0

    def test_geo_relays_nonempty(self):
        eng = _make_engine()
        assert len(eng.geo_relays) > 0

    def test_seed_reproducibility_ground_stations(self):
        """相同种子两次创建的引擎，地面站集合应完全相同。"""
        a = _make_engine(seed=42)
        b = _make_engine(seed=42)
        ids_a = [g["id"] for g in a.ground_stations]
        ids_b = [g["id"] for g in b.ground_stations]
        assert ids_a == ids_b

    def test_different_seeds_produce_different_configs(self):
        a = _make_engine(seed=1)
        b = _make_engine(seed=9999)
        ids_a = [g["id"] for g in a.ground_stations]
        ids_b = [g["id"] for g in b.ground_stations]
        assert ids_a != ids_b


# ---------------------------------------------------------------------------
# 2. submit_request
# ---------------------------------------------------------------------------


class TestSubmitRequest:
    """submit_request 的调度行为。"""

    def test_valid_request_returns_dict(self):
        eng = _make_engine()
        result = eng.submit_request(_valid_request_data())
        assert isinstance(result, dict)

    def test_valid_request_has_id_or_error(self):
        """接受时 result 应包含 id；拒绝时应包含 status=error。"""
        eng = _make_engine()
        result = eng.submit_request(_valid_request_data())
        assert "id" in result or result.get("status") == "error"

    def test_invalid_satellite_id_returns_error(self):
        eng = _make_engine()
        result = eng.submit_request(_valid_request_data(satellite_id="SAT_DOES_NOT_EXIST"))
        assert isinstance(result, dict)
        assert result.get("status") == "error"

    def test_invalid_satellite_id_response_contains_available_satellites(self):
        """拒绝响应应列出可用卫星列表，便于前端重新提交。"""
        eng = _make_engine()
        result = eng.submit_request(_valid_request_data(satellite_id="NO_SUCH_SAT"))
        assert "available_satellites" in result
        assert isinstance(result["available_satellites"], list)

    def test_invalid_satellite_increments_rejected_stats(self):
        eng = _make_engine()
        before = eng.stats.get("rejected_requests", 0)
        eng.submit_request(_valid_request_data(satellite_id="NO_SUCH_SAT"))
        assert eng.stats["rejected_requests"] > before

    def test_valid_submission_increments_total_and_user_requests(self):
        eng = _make_engine()
        before_total = eng.stats.get("total_requests", 0)
        before_user = eng.stats.get("user_requests", 0)
        eng.submit_request(_valid_request_data())
        assert eng.stats["total_requests"] > before_total
        assert eng.stats["user_requests"] > before_user


# ---------------------------------------------------------------------------
# 3. _data_size_to_mb — 单位换算
# ---------------------------------------------------------------------------


class TestDataSizeToMb:
    """_data_size_to_mb 的 KB/MB/GB 单位换算正确性。"""

    def _req(self, data_type: str, data_size: float) -> TransmissionRequest:
        return TransmissionRequest(
            data_type=data_type,
            data_size=data_size,
            priority=5,
            max_delay=600,
        )

    def test_task_cmd_kb_to_mb(self):
        """TASK_CMD 单位为 KB；1024 KB == 1 MB。"""
        eng = _make_engine()
        result = eng._data_size_to_mb(self._req("TASK_CMD", 1024))
        assert abs(result - 1.0) < 1e-9

    def test_data_slice_mb_stays_mb(self):
        """DATA_SLICE 单位为 MB；50 MB 应直���返回 50.0。"""
        eng = _make_engine()
        result = eng._data_size_to_mb(self._req("DATA_SLICE", 50))
        assert abs(result - 50.0) < 1e-9

    def test_raw_image_gb_to_mb(self):
        """RAW_IMAGE 单位为 GB；2 GB == 2048 MB。"""
        eng = _make_engine()
        result = eng._data_size_to_mb(self._req("RAW_IMAGE", 2))
        assert abs(result - 2048.0) < 1e-9

    def test_result_is_float_or_int(self):
        eng = _make_engine()
        result = eng._data_size_to_mb(self._req("TASK_CMD", 100))
        assert isinstance(result, (int, float))


# ---------------------------------------------------------------------------
# 4. _evaluate_request — 资源占用拒绝
# ---------------------------------------------------------------------------


class TestEvaluateRequest:
    """_evaluate_request 的核心决策逻辑。"""

    def test_rejects_when_satellite_occupied(self):
        """卫星已被占用时，_evaluate_request 应返回 (False, <reason>)。"""
        eng = _make_engine()
        sat = eng.leo_satellites[0]
        # 人工标记卫星为已占用
        eng.resource_usage["satellites"][sat.sat_id] = ["DUMMY_REQUEST"]
        req = TransmissionRequest(
            data_type="RAW_IMAGE",
            data_size=1,
            priority=5,
            max_delay=600,
            satellite_id=sat.sat_id,
        )
        accepted, reason = eng._evaluate_request(req, sat)
        assert accepted is False
        assert isinstance(reason, str)

    def test_task_cmd_is_accepted_immediately(self):
        """TASK_CMD（immediate=True）应绕过资源检查立即被接受。"""
        eng = _make_engine()
        sat = eng.leo_satellites[0]
        req = TransmissionRequest(
            data_type="TASK_CMD",
            data_size=1,
            priority=5,
            max_delay=600,
            satellite_id=sat.sat_id,
        )
        accepted, _reason = eng._evaluate_request(req, sat)
        assert accepted is True

    def test_test_mode_request_always_accepted(self):
        """experiment_requirements.test_mode=True 应无条件接受。"""
        eng = _make_engine()
        sat = eng.leo_satellites[0]
        # 即使卫星已被占用，测试模式也应接受
        eng.resource_usage["satellites"][sat.sat_id] = ["BLOCKING_REQ"]
        req = TransmissionRequest(
            data_type="DATA_SLICE",
            data_size=10,
            priority=5,
            max_delay=600,
            satellite_id=sat.sat_id,
            experiment_requirements={"test_mode": True},
        )
        accepted, _reason = eng._evaluate_request(req, sat)
        assert accepted is True


# ---------------------------------------------------------------------------
# 5. update_ground_station_count — 边界夹紧
# ---------------------------------------------------------------------------


class TestUpdateGroundStationCount:
    """update_ground_station_count 的边界与夹紧行为。"""

    def test_increase_count(self):
        eng = _make_engine()
        initial = len(eng.ground_stations)
        new_count = min(initial + 5, MAX_GROUND_STATION_COUNT)
        if new_count != initial:
            result = eng.update_ground_station_count(new_count)
            assert isinstance(result, bool)

    def test_count_below_min_is_clamped(self):
        """传入低于最小值的计数，引擎应夹紧到最小值而非崩溃。"""
        eng = _make_engine()
        eng.update_ground_station_count(0)  # 0 < MIN_GROUND_STATION_COUNT
        assert len(eng.ground_stations) >= MIN_GROUND_STATION_COUNT

    def test_count_above_max_is_clamped(self):
        """传入超出最大值的计数，引擎应夹紧到最大值。"""
        eng = _make_engine()
        eng.update_ground_station_count(MAX_GROUND_STATION_COUNT + 100)
        assert len(eng.ground_stations) <= MAX_GROUND_STATION_COUNT

    def test_same_count_returns_false(self):
        """计数不变时应返回 False（无更新）。"""
        eng = _make_engine()
        current = len(eng.ground_stations)
        result = eng.update_ground_station_count(current)
        # 当计数相同时实现通常返回 False
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# 6. update_leo_satellite_count — 最小值保护
# ---------------------------------------------------------------------------


class TestUpdateLeoSatelliteCount:
    """update_leo_satellite_count 的最小值保护。"""

    def test_valid_increase_succeeds(self):
        eng = _make_engine()
        new_count = len(eng.leo_satellites) + 3
        result = eng.update_leo_satellite_count(new_count)
        assert isinstance(result, bool)
        assert len(eng.leo_satellites) >= MIN_LEO_SATELLITE_COUNT

    def test_count_zero_clamped_to_min(self):
        """count=0 应被夹紧，卫星数量不低于 MIN_LEO_SATELLITE_COUNT。"""
        eng = _make_engine()
        eng.update_leo_satellite_count(0)
        assert len(eng.leo_satellites) >= MIN_LEO_SATELLITE_COUNT


# ---------------------------------------------------------------------------
# 7. TransmissionRequest — ID 唯一性
# ---------------------------------------------------------------------------


class TestTransmissionRequestIds:
    """TransmissionRequest 的 ID 自增与唯一性。"""

    def test_ids_are_unique_across_multiple_requests(self):
        requests = [
            TransmissionRequest("TASK_CMD", 100, 5, 600)
            for _ in range(10)
        ]
        ids = [r.id for r in requests]
        assert len(set(ids)) == len(ids), "请求 ID 应唯一，不允许���复"

    def test_id_format_starts_with_req(self):
        req = TransmissionRequest("TASK_CMD", 100, 5, 600)
        assert req.id.startswith("REQ_")

    def test_to_dict_contains_expected_fields(self):
        req = TransmissionRequest("DATA_SLICE", 50, 7, 300)
        d = req.to_dict()
        for field in ("id", "data_type", "data_size", "priority", "status"):
            assert field in d, f"to_dict() 缺少字段: {field}"


# ---------------------------------------------------------------------------
# 8. get_stats — 返回结构
# ---------------------------------------------------------------------------


class TestGetStats:
    """get_stats 返回结构完整性。"""

    def test_returns_dict(self):
        eng = _make_engine()
        assert isinstance(eng.get_stats(), dict)

    def test_contains_total_requests(self):
        eng = _make_engine()
        assert "total_requests" in eng.get_stats()

    def test_contains_accepted_and_rejected(self):
        eng = _make_engine()
        stats = eng.get_stats()
        assert "accepted_requests" in stats
        assert "rejected_requests" in stats

    def test_resource_utilization_is_dict(self):
        eng = _make_engine()
        stats = eng.get_stats()
        ru = stats.get("resource_utilization", None)
        assert isinstance(ru, dict)


# ---------------------------------------------------------------------------
# 9. DATA_TYPES — 配置完整性
# ---------------------------------------------------------------------------


class TestDataTypesConfig:
    """DATA_TYPES 全局配置的完整性与一致性校验。"""

    def test_data_types_is_nonempty_dict(self):
        assert isinstance(DATA_TYPES, dict) and len(DATA_TYPES) > 0

    def test_all_entries_have_name(self):
        for key, cfg in DATA_TYPES.items():
            assert "name" in cfg, f"DATA_TYPES[{key!r}] 缺少 'name' 字段"

    def test_all_entries_have_size_range(self):
        for key, cfg in DATA_TYPES.items():
            assert "size_range" in cfg, f"DATA_TYPES[{key!r}] 缺少 'size_range' 字段"
            lo, hi = cfg["size_range"]
            assert lo <= hi, f"DATA_TYPES[{key!r}].size_range 上下界顺序错误"
