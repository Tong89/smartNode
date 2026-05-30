# -*- coding: utf-8 -*-
"""场景资源定义的外置加载。

将地面站 / LEO / GEO / 数据类型等资源定义外置到数据文件（JSON），通过 ``load_scenario`` 读取，
便于在不改代码的前提下切换/扩展场景。LEO 由轨道根数还原为 OrbitalElements。
"""
import json
import os

from backend.orbit import OrbitalElements

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
DEFAULT_SCENARIO = os.path.join(DATA_DIR, "scenario.default.json")


def load_scenario(path=None):
    """加载场景资源定义，返回 dict(ground_stations, leo_satellites, geo_relays, data_types)。

    leo_satellites 还原为 OrbitalElements 对象；其余保持 dict 结构以兼容现有引擎。
    """
    path = path or DEFAULT_SCENARIO
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    leo = [
        OrbitalElements(
            name=s["name"], sat_id=s["sat_id"], semi_major_axis=s["a"], eccentricity=s["e"],
            inclination=s["i"], raan=s["raan"], arg_perigee=s["omega"], mean_anomaly=s["M0"],
        )
        for s in raw.get("leo_satellites", [])
    ]

    data_types = {}
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
