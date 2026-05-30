# -*- coding: utf-8 -*-
"""SGP4/TLE 轨道传播器（统一接口）。

提供 ``propagate_tle`` 与 ``Propagator`` 类，封装 sgp4 库的 TLE 解析和 ECI 传播，
并通过统一接口 ``propagate(t) -> (lat°, lon°, alt_m)`` 对上层模块透明。

当卫星配置了有效的 TLE 时，使用 SGP4 进行高精度传播；否则回退到现有开普勒二体
解析解，行为与重构前一致。

坐标输出经由 :mod:`backend.physics.coordinates` 的 ECI/ECEF/LLA 转换链处理。
长度单位：内部 km，高度对外以 m 返回（与 OrbitalElements.propagate 一致）。
"""
from __future__ import annotations

import math
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from backend.physics.coordinates import ecef_to_lla, eci_to_ecef, OMEGA_EARTH

logger = logging.getLogger("smartnode.physics.propagator")

# ---------------------------------------------------------------------------
# J2 摄动常量
# ---------------------------------------------------------------------------

#: 地球引力常数 (km³/s²)
MU_EARTH: float = 398600.4418
#: 地球赤道半径 (km)
R_EARTH_KM: float = 6378.137
#: J2 带谐系数（WGS-84）
J2: float = 1.08262668e-3

# ---------------------------------------------------------------------------
# TLE 解析与 SGP4 传播（可选依赖，优雅降级）
# ---------------------------------------------------------------------------
try:
    from sgp4.api import Satrec, WGS72
    from sgp4.conveniences import sat_epoch_datetime
    _SGP4_AVAILABLE = True
except ImportError:  # pragma: no cover
    _SGP4_AVAILABLE = False
    logger.warning(
        "sgp4 库未安装，TLE 传播不可用，所有卫星将回退二体开普勒解析解。"
        "请运行 'pip install sgp4>=2.22' 启用 SGP4 支持。"
    )


# ---------------------------------------------------------------------------
# ECI -> LLA 转换辅助
# ---------------------------------------------------------------------------

def _eci_to_lla(x_km: float, y_km: float, z_km: float, gst_rad: float) -> Tuple[float, float, float]:
    """ECI(km) -> (lat°, lon°, alt_m) via ECEF，使用 WGS-84 椭球。"""
    x_ecef, y_ecef, z_ecef = eci_to_ecef(x_km, y_km, z_km, gst_rad)
    return ecef_to_lla(x_ecef, y_ecef, z_ecef)


def _gmst(t: datetime) -> float:
    """格林尼治平恒星时 (GMST) 近似，返回弧度。

    使用简化公式（精度约 0.5 弧秒）：
    GMST = 100.4606184 + 36000.77004 * T0 + 0.000387933 * T0^2 + ω_earth * UT1
    其中 T0 是自 J2000.0 (2000-01-01 12:00 UTC) 起的儒略世纪数。
    """
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    # 儒略日 (简化)
    jd = (t - datetime(1858, 11, 17, tzinfo=timezone.utc)).total_seconds() / 86400.0 + 2400000.5
    t0 = (jd - 2451545.0) / 36525.0          # 自 J2000.0 的儒略世纪
    theta_deg = (
        280.46061837
        + 360.98564736629 * (jd - 2451545.0)
        + 0.000387933 * t0 * t0
    )
    return math.radians(theta_deg % 360.0)


# ---------------------------------------------------------------------------
# J2 长期摄动速率
# ---------------------------------------------------------------------------

def j2_raan_rate(a: float, e: float, i_deg: float) -> float:
    """升交点赤经 (RAAN) 因 J2 引起的长期进动速率 (rad/s)。

    公式（一阶 J2 长期项）::

        dΩ/dt = -(3/2) * n * J2 * (R_e/p)² * cos(i)

    其中 p = a(1 - e²) 为半通径，n 为平均角速度。

    参数
    ----
    a : float
        轨道半长轴 (km)。
    e : float
        轨道离心率 (无量纲)。
    i_deg : float
        轨道倾角 (°)。

    返回
    ----
    float
        RAAN 进动速率 (rad/s)；负值表示向西进动（顺行轨道）。
    """
    n = math.sqrt(MU_EARTH / a ** 3)           # rad/s
    p = a * (1.0 - e * e)                       # 半通径 km
    cos_i = math.cos(math.radians(i_deg))
    return -1.5 * n * J2 * (R_EARTH_KM / p) ** 2 * cos_i


def j2_arg_perigee_rate(a: float, e: float, i_deg: float) -> float:
    """近地点幅角 (ω) 因 J2 引起的长期进动速率 (rad/s)。

    公式::

        dω/dt = (3/2) * n * J2 * (R_e/p)² * (2 - (5/2)*sin²(i))

    参数
    ----
    a : float
        轨道半长轴 (km)。
    e : float
        轨道离心率 (无量纲)。
    i_deg : float
        轨道倾角 (°)。

    返回
    ----
    float
        近地点幅角进动速率 (rad/s)。
    """
    n = math.sqrt(MU_EARTH / a ** 3)
    p = a * (1.0 - e * e)
    sin2_i = math.sin(math.radians(i_deg)) ** 2
    return 1.5 * n * J2 * (R_EARTH_KM / p) ** 2 * (2.0 - 2.5 * sin2_i)


def j2_mean_anomaly_rate_correction(a: float, e: float, i_deg: float) -> float:
    """平近点角 (M) 因 J2 引起的长期修正速率 (rad/s)，在平均角速度 n 基础上的附加量。

    公式（J2 对平均角速度的一阶修正）::

        dM/dt|J2 = (3/2) * n * J2 * (R_e/p)² * sqrt(1-e²) * (1 - (3/2)*sin²(i))

    参数
    ----
    a : float
        轨道半长轴 (km)。
    e : float
        轨道离心率 (无量纲)。
    i_deg : float
        轨道倾角 (°)。

    返回
    ----
    float
        平近点角速率附加修正量 (rad/s)。
    """
    n = math.sqrt(MU_EARTH / a ** 3)
    p = a * (1.0 - e * e)
    eta = math.sqrt(1.0 - e * e)
    sin2_i = math.sin(math.radians(i_deg)) ** 2
    return 1.5 * n * J2 * (R_EARTH_KM / p) ** 2 * eta * (1.0 - 1.5 * sin2_i)


# ---------------------------------------------------------------------------
# 公开的低级函数
# ---------------------------------------------------------------------------

def propagate_tle(
    tle_line1: str,
    tle_line2: str,
    t: datetime,
) -> Tuple[float, float, float]:
    """使用 SGP4 由 TLE 两行根数传播卫星位置。

    参数
    ----
    tle_line1 : str
        TLE 第一行（74 字符 NORAD 格式）。
    tle_line2 : str
        TLE 第二行（74 字符 NORAD 格式）。
    t : datetime
        目标时刻（支持无时区 naive datetime，视为 UTC）。

    返回
    ----
    (lat, lon, alt) : tuple[float, float, float]
        纬度（°）、经度（°）、高度（m）。

    异常
    ----
    RuntimeError
        sgp4 库不可用时抛出。
    ValueError
        SGP4 传播失败（e.g. 轨道衰减或 TLE 格式错误）。
    """
    if not _SGP4_AVAILABLE:
        raise RuntimeError("sgp4 库不可用，无法执行 TLE 传播。请安装 sgp4>=2.22。")

    satellite = Satrec.twoline2rv(tle_line1, tle_line2)

    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)

    jd_whole = math.floor(t.timestamp() / 86400.0) + 2440587.5
    jd_frac = (t.timestamp() % 86400.0) / 86400.0

    # sgp4 使用整数与小数分开的儒略日以保持精度
    e, r, v = satellite.sgp4(jd_whole, jd_frac)
    if e != 0:
        raise ValueError(
            f"SGP4 传播错误 (error code {e})：轨道可能已衰减或 TLE 数据无效。"
        )

    # r 为 ECI 位置向量 (km/s 框架中 km 单位)
    x_km, y_km, z_km = r
    gst = _gmst(t)
    return _eci_to_lla(x_km, y_km, z_km, gst)


# ---------------------------------------------------------------------------
# 高级封装类
# ---------------------------------------------------------------------------

class Propagator:
    """统一轨道传播接口：TLE/SGP4 优先，二体开普勒回退。

    用法示例::

        # 1. 从 TLE 字符串创建（走 SGP4 路径）
        prop = Propagator.from_tle("卫星名", "1 25544U ...", "2 25544 ...")
        lat, lon, alt = prop.propagate(datetime.utcnow())

        # 2. 从轨道根数创建（走二体回退路径）
        from backend.orbit import OrbitalElements
        oe = OrbitalElements("遥感一号", "LEO_001", 6871, 0.001, 97.4, 0, 0, 0)
        prop = Propagator.from_orbital_elements(oe)
        lat, lon, alt = prop.propagate(datetime.utcnow())
    """

    def __init__(
        self,
        name: str,
        tle_line1: Optional[str] = None,
        tle_line2: Optional[str] = None,
        orbital_elements=None,
    ) -> None:
        """
        参数
        ----
        name : str
            卫星名称（用于日志）。
        tle_line1 : str, optional
            TLE 第一行；非 None 且 sgp4 可用时启用 SGP4 路径。
        tle_line2 : str, optional
            TLE 第二行；需与 tle_line1 同时提供。
        orbital_elements : OrbitalElements, optional
            二体回退轨道根数对象；TLE 无效时使用。
        """
        self.name = name
        self._tle1 = tle_line1
        self._tle2 = tle_line2
        self._oe = orbital_elements
        self._use_sgp4 = (
            _SGP4_AVAILABLE
            and tle_line1 is not None
            and tle_line2 is not None
        )
        if self._use_sgp4:
            try:
                self._sat = Satrec.twoline2rv(tle_line1, tle_line2)
                logger.debug("Propagator[%s]: SGP4 模式已初始化", name)
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning(
                    "Propagator[%s]: TLE 解析失败（%s），回退二体。", name, exc
                )
                self._use_sgp4 = False
        if not self._use_sgp4:
            if orbital_elements is None:
                raise ValueError(
                    f"Propagator '{name}': 需提供有效 TLE 或 OrbitalElements 之一。"
                )
            logger.debug("Propagator[%s]: 二体开普勒模式", name)

    # ------------------------------------------------------------------
    # 工厂方法
    # ------------------------------------------------------------------

    @classmethod
    def from_tle(
        cls,
        name: str,
        tle_line1: str,
        tle_line2: str,
        orbital_elements=None,
    ) -> "Propagator":
        """由 TLE 两行根数创建传播器；若 sgp4 不可用则需提供 orbital_elements 回退。"""
        return cls(
            name=name,
            tle_line1=tle_line1,
            tle_line2=tle_line2,
            orbital_elements=orbital_elements,
        )

    @classmethod
    def from_orbital_elements(cls, oe) -> "Propagator":
        """由 :class:`~backend.orbit.OrbitalElements` 创建二体传播器。

        若 oe 对象带有 ``tle_line1`` / ``tle_line2`` 属性且非空，则优先走 SGP4。
        """
        tle1 = getattr(oe, "tle_line1", None)
        tle2 = getattr(oe, "tle_line2", None)
        return cls(
            name=oe.name,
            tle_line1=tle1,
            tle_line2=tle2,
            orbital_elements=oe,
        )

    # ------------------------------------------------------------------
    # 核心传播接口
    # ------------------------------------------------------------------

    def propagate(self, t: datetime) -> Tuple[float, float, float]:
        """计算 t 时刻卫星位置。

        参数
        ----
        t : datetime
            目标时刻（naive 视为 UTC）。

        返回
        ----
        (lat, lon, alt) : tuple[float, float, float]
            纬度（°）、经度（°）、高度（m）。
        """
        if self._use_sgp4:
            return self._propagate_sgp4(t)
        return self._oe.propagate(t)

    def propagate_eci(self, t: datetime) -> Tuple[float, float, float]:
        """返回 ECI 位置向量 (x_km, y_km, z_km)（仅 SGP4 路径；二体路径抛出 NotImplementedError）。"""
        if not self._use_sgp4:
            raise NotImplementedError("二体路径暂不返回 ECI 向量，请使用 propagate()。")
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        jd_whole = math.floor(t.timestamp() / 86400.0) + 2440587.5
        jd_frac = (t.timestamp() % 86400.0) / 86400.0
        e, r, _ = self._sat.sgp4(jd_whole, jd_frac)
        if e != 0:
            raise ValueError(f"SGP4 传播错误 (code {e})")
        return tuple(r)

    @property
    def uses_sgp4(self) -> bool:
        """当前实例是否使用 SGP4 传播。"""
        return self._use_sgp4

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------

    def _propagate_sgp4(self, t: datetime) -> Tuple[float, float, float]:
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        jd_whole = math.floor(t.timestamp() / 86400.0) + 2440587.5
        jd_frac = (t.timestamp() % 86400.0) / 86400.0
        e, r, _ = self._sat.sgp4(jd_whole, jd_frac)
        if e != 0:
            # 回退到二体（如果可用）
            if self._oe is not None:
                logger.warning(
                    "Propagator[%s]: SGP4 错误 code=%d，本次回退二体。", self.name, e
                )
                return self._oe.propagate(t)
            raise ValueError(
                f"Propagator[{self.name}]: SGP4 传播失败 (code {e})，且无二体回退。"
            )
        x_km, y_km, z_km = r
        gst = _gmst(t)
        return _eci_to_lla(x_km, y_km, z_km, gst)

    def __repr__(self) -> str:
        mode = "SGP4" if self._use_sgp4 else "Kepler"
        return f"<Propagator name={self.name!r} mode={mode}>"
