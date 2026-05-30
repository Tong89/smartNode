# -*- coding: utf-8 -*-
"""数据模型 dataclass 的 from_dict/to_dict 与现有 JSON 契约一致性测试。"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.models import GeoRelay, GroundStation, LeoSatellite  # noqa: E402
from backend.constellation import CHINA_GROUND_STATIONS, GEO_RELAY_SATELLITES  # noqa: E402


def test_ground_station_roundtrip_preserves_contract():
    raw = CHINA_GROUND_STATIONS[0]
    gs = GroundStation.from_dict(raw)
    assert gs.id == raw["id"] and gs.name == raw["name"]
    out = gs.to_dict()
    for key in ("id", "name", "lat", "lon", "antenna_type", "max_links"):
        assert out[key] == raw[key]


def test_geo_relay_roundtrip():
    raw = GEO_RELAY_SATELLITES[0]
    relay = GeoRelay.from_dict(raw)
    assert relay.id == raw["id"]
    out = relay.to_dict()
    assert out["id"] == raw["id"] and out["bandwidth"] == raw.get("bandwidth", 2000)


def test_leo_satellite_model():
    sat = LeoSatellite.from_dict({"id": "LEO_001", "name": "x", "lat": 1.0, "lon": 2.0, "alt": 500000.0})
    d = sat.to_dict()
    assert d["id"] == "LEO_001" and d["alt"] == 500000.0
