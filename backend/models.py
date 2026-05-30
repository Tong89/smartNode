# -*- coding: utf-8 -*-
"""统一数据模型（dataclass + 类型注解）。

为地面站 / GEO 中继 / LEO 卫星等提供类型化模型与 from_dict/to_dict 适配，消除 gs['id'] 与属性
访问混用的隐患，并为 mypy 检查打基础。为保持与前端 JSON 契约一致，to_dict 输出字段与原 dict 一致。

当前以**适配层**形态引入：引擎内部仍可沿用原 dict 结构，新代码/测试可使用类型化模型；后续可渐进迁移。
"""
from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class GroundStation:
    id: str
    name: str
    lat: float
    lon: float
    antenna_type: str
    max_links: int = 1

    @classmethod
    def from_dict(cls, d: dict) -> "GroundStation":
        return cls(
            id=d["id"], name=d["name"], lat=d["lat"], lon=d["lon"],
            antenna_type=d.get("antenna_type", "X"), max_links=d.get("max_links", 1),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GeoRelay:
    id: str
    name: str
    lon: float
    bandwidth: int = 2000
    antenna: Optional[str] = None
    beams: Optional[int] = None

    @classmethod
    def from_dict(cls, d: dict) -> "GeoRelay":
        return cls(
            id=d["id"], name=d["name"], lon=d.get("lon", 0),
            bandwidth=d.get("bandwidth", 2000), antenna=d.get("antenna"), beams=d.get("beams"),
        )

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class LeoSatellite:
    id: str
    name: str
    lat: float
    lon: float
    alt: float
    orbit_period: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> "LeoSatellite":
        return cls(
            id=d["id"], name=d["name"], lat=d["lat"], lon=d["lon"], alt=d["alt"],
            orbit_period=d.get("orbit_period", 0.0),
        )

    def to_dict(self) -> dict:
        return asdict(self)
