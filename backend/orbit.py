# -*- coding: utf-8 -*-
"""轨道与几何计算（无状态纯函数 + 轨道根数模型）。

从 core.py 抽离：calc_central_angle、OrbitalElements（二体传播 + 可选 SGP4/TLE）、
可见性与各类链路速率计算。本模块不依赖引擎实例，可独立导入与单测；引擎通过导入复用，
数值与抽离前一致。

TLE 集成
---------
``OrbitalElements`` 新增可选 ``tle_line1`` / ``tle_line2`` 字段。当这两个字段
非空且 ``sgp4`` 已安装时，``propagate()`` 自动走 SGP4 高精度路径；否则继续使用
现有开普勒二体解析解。对调用者接口（返回 ``(lat, lon, alt)``）无影响。
"""
import math
from datetime import datetime

from backend.physics.coordinates import ecef_to_lla, eci_to_ecef


def calc_central_angle(lat1, lon1, lat2, lon2):
    """计算球面大圆地心角 (Degrees)"""
    rad = math.pi / 180.0
    phi1, phi2 = lat1 * rad, lat2 * rad
    dphi = (lat2 - lat1) * rad
    dlam = (lon2 - lon1) * rad
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return c * 180.0 / math.pi


class OrbitalElements:
    """轨道六根数定义 - 用于精确计算卫星位置。

    支持可选的 TLE 两行根数驱动 SGP4 传播。当 ``tle_line1`` / ``tle_line2`` 字段
    非空时，``propagate()`` 使用 :func:`~backend.physics.propagator.propagate_tle`；
    否则回退现有开普勒二体解析解，行为与重构前完全一致。

    参数
    ----
    tle_line1 : str, optional
        TLE 第一行（74 字符 NORAD 格式）。
    tle_line2 : str, optional
        TLE 第二行（74 字符 NORAD 格式）。
    """

    def __init__(self, name, sat_id,
                 semi_major_axis, eccentricity, inclination,
                 raan, arg_perigee, mean_anomaly, epoch=None,
                 tle_line1=None, tle_line2=None):
        self.name = name
        self.sat_id = sat_id
        self.a = semi_major_axis
        self.e = eccentricity
        self.i = inclination
        self.raan = raan
        self.omega = arg_perigee
        self.M0 = mean_anomaly
        self.epoch = epoch or datetime.now()
        self.mu = 398600.4418   # 地球引力常数 (km³/s²)
        self.R_earth = 6371.0   # 地球半径 (km)
        # 可选 TLE 字段（非空时启用 SGP4 传播）
        self.tle_line1 = tle_line1
        self.tle_line2 = tle_line2
        # 延迟初始化 Propagator（避免循环导入问题）
        self._propagator = None

    def _get_propagator(self):
        """惰性构建并缓存 Propagator 实例。"""
        if self._propagator is None:
            from backend.physics.propagator import Propagator  # pylint: disable=import-outside-toplevel
            self._propagator = Propagator.from_orbital_elements(self)
        return self._propagator

    def get_mean_motion(self):
        return math.sqrt(self.mu / (self.a ** 3))

    def get_orbital_period(self):
        return 2 * math.pi * math.sqrt((self.a ** 3) / self.mu)

    def get_altitude(self):
        return (self.a - self.R_earth) * 1000

    def propagate(self, current_time):
        """根据当前时间计算卫星位置，返回 (lat°, lon°, alt m)。

        若设置了有效 TLE 且 sgp4 可用，使用 SGP4 传播；否则回退二体开普勒解析解。
        """
        # 若存在 TLE 且 SGP4 可用，委托给统一传播器
        if self.tle_line1 and self.tle_line2:
            prop = self._get_propagator()
            if prop.uses_sgp4:
                return prop.propagate(current_time)
            # sgp4 库未安装或 TLE 解析失败，回退二体（避免无限递归）
        return self._propagate_kepler(current_time)

    def _propagate_kepler(self, current_time):
        """开普勒二体解析传播，返回 (lat°, lon°, alt m)。"""
        if isinstance(current_time, datetime):
            dt_seconds = (current_time - self.epoch).total_seconds()
        else:
            dt_seconds = current_time

        n = self.get_mean_motion()
        M = math.radians(self.M0) + n * dt_seconds
        M = M % (2 * math.pi)

        E = M
        for _ in range(10):
            E = M + self.e * math.sin(E)

        nu = 2 * math.atan2(
            math.sqrt(1 + self.e) * math.sin(E / 2),
            math.sqrt(1 - self.e) * math.cos(E / 2)
        )

        r = self.a * (1 - self.e * math.cos(E))
        x_orb = r * math.cos(nu)
        y_orb = r * math.sin(nu)

        cos_O = math.cos(math.radians(self.raan))
        sin_O = math.sin(math.radians(self.raan))
        cos_i = math.cos(math.radians(self.i))
        sin_i = math.sin(math.radians(self.i))
        cos_w = math.cos(math.radians(self.omega))
        sin_w = math.sin(math.radians(self.omega))

        x = (cos_O * cos_w - sin_O * sin_w * cos_i) * x_orb + \
            (-cos_O * sin_w - sin_O * cos_w * cos_i) * y_orb
        y = (sin_O * cos_w + cos_O * sin_w * cos_i) * x_orb + \
            (-sin_O * sin_w + cos_O * cos_w * cos_i) * y_orb
        z = (sin_w * sin_i) * x_orb + (cos_w * sin_i) * y_orb

        omega_earth = 7.292115e-5
        theta = omega_earth * dt_seconds

        x_ecef, y_ecef, z_ecef = eci_to_ecef(x, y, z, theta)
        lat, lon, alt = ecef_to_lla(x_ecef, y_ecef, z_ecef)
        return lat, lon, alt

    @classmethod
    def from_tle(cls, name: str, sat_id: str,
                 tle_line1: str, tle_line2: str,
                 epoch=None) -> "OrbitalElements":
        """由 TLE 两行根数构造 OrbitalElements，轨道根数从 TLE 解析填充。

        SGP4 传播时直接使用 TLE 数据；轨道根数字段仅用于回退和元数据。

        参数
        ----
        name : str
            卫星名称。
        sat_id : str
            系统内部卫星 ID。
        tle_line1 : str
            TLE 第一行。
        tle_line2 : str
            TLE 第二行。
        epoch : datetime, optional
            TLE 历元（None 则从 TLE 解析，回退 datetime.now()）。

        返回
        ----
        OrbitalElements
            带有 TLE 字段的实例，propagate() 将走 SGP4 路径。
        """
        # 从 TLE 第二行解析轨道根数（用于回退/元数据）
        try:
            fields = tle_line2.split()
            inclination = float(fields[2])
            raan = float(fields[3])
            eccentricity = float("0." + fields[4])
            arg_perigee = float(fields[5])
            mean_anomaly = float(fields[6])
            mean_motion_rev_day = float(fields[7][:11])
            # 由平运动推算半长轴 (km)
            mu = 398600.4418
            n_rad_s = mean_motion_rev_day * 2.0 * math.pi / 86400.0
            semi_major_axis = (mu / (n_rad_s ** 2)) ** (1.0 / 3.0)
        except (IndexError, ValueError):
            # TLE 解析失败时使用保守默认值（SGP4 仍可正常运行）
            inclination = 0.0
            raan = 0.0
            eccentricity = 0.0
            arg_perigee = 0.0
            mean_anomaly = 0.0
            semi_major_axis = 7000.0  # ~629 km LEO

        return cls(
            name=name,
            sat_id=sat_id,
            semi_major_axis=semi_major_axis,
            eccentricity=eccentricity,
            inclination=inclination,
            raan=raan,
            arg_perigee=arg_perigee,
            mean_anomaly=mean_anomaly,
            epoch=epoch,
            tle_line1=tle_line1,
            tle_line2=tle_line2,
        )


def check_visibility(sat_pos, gs_pos, min_elevation=10):
    """检查卫星与地面站的可见性（仰角 >= min_elevation）。"""
    angle = calc_central_angle(sat_pos["lat"], sat_pos["lon"], gs_pos["lat"], gs_pos["lon"])
    R = 6371.0
    h = sat_pos["alt"] / 1000.0
    d = R * math.radians(angle)
    if d < 0.001:
        elevation = 90.0
    else:
        slant_range = math.sqrt(R * R + (R + h) * (R + h) - 2 * R * (R + h) * math.cos(math.radians(angle)))
        elevation = math.degrees(math.asin((R + h) * math.sin(math.radians(angle)) / slant_range)) - angle
    return elevation >= min_elevation


def check_geo_visibility(leo_pos, geo_pos):
    """检查 LEO 与 GEO 中继星的可见性。"""
    angle = calc_central_angle(leo_pos["lat"], leo_pos["lon"], geo_pos["lat"], geo_pos["lon"])
    return angle < 80


def calculate_direct_rate(sat_pos, gs, data_type=None):
    """直连链路速率 (Mbps)。"""
    angle = calc_central_angle(sat_pos["lat"], sat_pos["lon"], gs["lat"], gs["lon"])
    distance = math.sqrt((sat_pos["alt"] / 1000) ** 2 + (6371 * math.sin(math.radians(angle))) ** 2)
    base_rate = 200 if gs["antenna_type"] == "Ka" else 100
    rate = base_rate * math.exp(-distance / 10000)
    if data_type == "RAW_IMAGE":
        rate = rate * 0.6
    return max(rate, 5)


def calculate_relay_rate(sat_pos, geo_pos, gs, data_type=None):
    """单跳中继链路速率 (Mbps)。"""
    angle1 = calc_central_angle(sat_pos["lat"], sat_pos["lon"], geo_pos["lat"], geo_pos["lon"])
    dist1 = math.sqrt((geo_pos["alt"] - sat_pos["alt"]) ** 2 / 1e12 + (6371 * math.sin(math.radians(angle1))) ** 2)
    rate1 = 500 * math.exp(-dist1 / 50000)
    angle2 = calc_central_angle(geo_pos["lat"], geo_pos["lon"], gs["lat"], gs["lon"])
    dist2 = math.sqrt((geo_pos["alt"] / 1000) ** 2 + (6371 * math.sin(math.radians(angle2))) ** 2)
    rate2 = 400 * math.exp(-dist2 / 40000)
    rate = min(rate1, rate2)
    if data_type == "RAW_IMAGE":
        rate = rate * 0.6
    return max(rate, 5)


def calculate_inter_satellite_rate(geo1_pos, geo2_pos):
    """GEO 星间链路速率 (Mbps)。"""
    angle = calc_central_angle(geo1_pos["lat"], geo1_pos["lon"], geo2_pos["lat"], geo2_pos["lon"])
    dist = 2 * geo1_pos["alt"] / 1000 * math.sin(math.radians(angle) / 2)
    rate = 2000 * math.exp(-dist / 40000)
    return max(rate, 100)


def calculate_multi_hop_relay_rate(sat_pos, geo1_pos, geo2_pos, gs, data_type=None):
    """多跳中继链路速率 (Mbps) - LEO→GEO1→GEO2→地面站。"""
    angle1 = calc_central_angle(sat_pos["lat"], sat_pos["lon"], geo1_pos["lat"], geo1_pos["lon"])
    dist1 = math.sqrt((geo1_pos["alt"] - sat_pos["alt"]) ** 2 / 1e12 + (6371 * math.sin(math.radians(angle1))) ** 2)
    rate1 = 1500 * math.exp(-dist1 / 30000)
    rate2 = calculate_inter_satellite_rate(geo1_pos, geo2_pos)
    angle3 = calc_central_angle(geo2_pos["lat"], geo2_pos["lon"], gs["lat"], gs["lon"])
    dist3 = math.sqrt((geo2_pos["alt"] / 1000) ** 2 + (6371 * math.sin(math.radians(angle3))) ** 2)
    rate3 = 1000 * math.exp(-dist3 / 20000)
    rate = min(rate1, rate2, rate3)
    if data_type == "RAW_IMAGE":
        rate = rate * 0.5
    return rate
