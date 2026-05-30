# -*- coding: utf-8 -*-
"""基于工厂模式的引擎单测：轨道传播确定性、可见性、submit 契约、种子可复现。"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend import orbit  # noqa: E402
from backend.core import create_engine  # noqa: E402


def test_orbit_propagation_deterministic():
    e = create_engine(seed=1, autostart=False)
    sat = e.leo_satellites[0]
    p1 = sat.propagate(1000.0)
    p2 = sat.propagate(1000.0)
    assert p1 == p2  # 同一时刻传播确定
    assert all(v == v for v in p1)  # 非 NaN


def test_visibility_pure_function():
    overhead = {"lat": 39.9, "lon": 116.4, "alt": 500000}
    gs = {"lat": 39.9, "lon": 116.4, "antenna_type": "Ka"}
    assert orbit.check_visibility(overhead, gs) is True  # 正上方可见
    far = {"lat": -39.9, "lon": -63.6, "alt": 500000}
    assert orbit.check_visibility(far, gs) is False  # 对跖点不可见


def test_submit_request_returns_dict_contract():
    e = create_engine(seed=2, autostart=False)
    res = e.submit_request({"data_type": "TASK_CMD", "data_size": 10, "priority": 8, "max_delay": 600})
    assert isinstance(res, dict) and "status" in res
    bad = e.submit_request({"data_type": "TASK_CMD", "data_size": 10, "priority": 8, "max_delay": 600, "satellite_id": "NOPE"})
    assert bad.get("status") == "error"


def test_seed_reproducibility():
    a = create_engine(seed=42, autostart=False)
    b = create_engine(seed=42, autostart=False)
    assert [g["id"] for g in a.ground_stations] == [g["id"] for g in b.ground_stations]
