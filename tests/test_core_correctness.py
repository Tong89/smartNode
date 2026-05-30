# -*- coding: utf-8 -*-
"""回归测试：覆盖 M1 主题线的正确性修复（占用判定 / 单位换算 / 返回类型 / 背景任务）。

不启动 Flask、不依赖网络与真实时间推进：创建独立 SimulationEngine 并立即停止后台线程。
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.core import SimulationEngine, TransmissionRequest, DATA_TYPES  # noqa: E402


def make_engine():
    eng = SimulationEngine(ground_station_count=5, leo_satellite_count=4)
    eng.running = False  # 停止后台线程，保证测试确定性
    return eng


def test_submit_request_invalid_satellite_returns_dict():
    eng = make_engine()
    result = eng.submit_request({
        "data_type": "TASK_CMD", "data_size": 10, "priority": 8,
        "max_delay": 600, "satellite_id": "NO_SUCH_SAT",
    })
    assert isinstance(result, dict)
    assert result.get("status") == "error"


def test_data_size_to_mb_unit_conversion():
    eng = make_engine()

    def req(dt, size):
        return TransmissionRequest(data_type=dt, data_size=size, priority=5, max_delay=600)

    # TASK_CMD=KB, DATA_SLICE=MB, RAW_IMAGE=GB
    assert abs(eng._data_size_to_mb(req("TASK_CMD", 1024)) - 1.0) < 1e-9     # 1024 KB -> 1 MB
    assert abs(eng._data_size_to_mb(req("DATA_SLICE", 50)) - 50.0) < 1e-9    # 50 MB -> 50 MB
    assert abs(eng._data_size_to_mb(req("RAW_IMAGE", 2)) - 2048.0) < 1e-9    # 2 GB -> 2048 MB


def test_evaluate_request_rejects_when_satellite_occupied():
    eng = make_engine()
    sat = eng.leo_satellites[0]
    eng.resource_usage["satellites"][sat.sat_id] = ["REQ_OTHER"]  # 占用该卫星
    req = TransmissionRequest(data_type="RAW_IMAGE", data_size=1, priority=5,
                              max_delay=600, satellite_id=sat.sat_id)
    accepted, _reason = eng._evaluate_request(req, sat)
    assert accepted is False


def test_background_task_data_types_have_size_range():
    # _generate_background_tasks 依赖 size_range（而非已删除的 typical_size）
    for dt in ("TASK_CMD", "INTEL", "DATA_SLICE"):
        cfg = DATA_TYPES[dt]
        assert "size_range" in cfg
        lo, hi = cfg["size_range"]
        assert lo <= hi
