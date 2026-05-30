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
from backend.physics.propagator import (
    j2_raan_rate,
    j2_arg_perigee_rate,
    j2_mean_anomaly_rate_correction,
)
from backend.physics.geometry import (
    check_visibility_enu,
    check_geo_visibility_enu,
    compute_look_angles,
)
from backend.comms.link_budget import (
    link_budget_direct,
    link_budget_relay,
    link_budget_inter_satellite,
)


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
                 tle_line1=None, tle_line2=None,
                 j2_perturbation=True):
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
        # J2 摄动开关（默认开启；设为 False 可禁用以复现纯二体结果）
        self.j2_perturbation = j2_perturbation
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
        """开普勒二体解析传播（可选 J2 摄动修正），返回 (lat°, lon°, alt m)。

        当 ``self.j2_perturbation`` 为 ``True``（默认）时，在二体开普勒传播基础上
        叠加 J2 带谐系数引起的长期摄动修正：

        * 升交点赤经 (RAAN) 进动：dΩ/dt = -(3/2) n J2 (Rₑ/p)² cos i
        * 近地点幅角漂移：dω/dt = (3/2) n J2 (Rₑ/p)² (2 - 5/2 sin²i)
        * 平近点角速率修正：dM/dt += (3/2) n J2 (Rₑ/p)² √(1-e²) (1 - 3/2 sin²i)

        仅作用于二体回退路径（SGP4 路径已内含摄动，不重复）。
        """
        if isinstance(current_time, datetime):
            dt_seconds = (current_time - self.epoch).total_seconds()
        else:
            dt_seconds = current_time

        n = self.get_mean_motion()

        # ---- J2 长期摄动修正 -----------------------------------------------
        if self.j2_perturbation:
            # 各轨道要素在 dt 内的长期漂移量（弧度）
            n_M_corr = j2_mean_anomaly_rate_correction(self.a, self.e, self.i)
            raan_rad = math.radians(self.raan) + j2_raan_rate(
                self.a, self.e, self.i
            ) * dt_seconds
            omega_rad = math.radians(self.omega) + j2_arg_perigee_rate(
                self.a, self.e, self.i
            ) * dt_seconds
            M = math.radians(self.M0) + (n + n_M_corr) * dt_seconds
        else:
            raan_rad = math.radians(self.raan)
            omega_rad = math.radians(self.omega)
            M = math.radians(self.M0) + n * dt_seconds
        # -----------------------------------------------------------------------

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

        cos_O = math.cos(raan_rad)
        sin_O = math.sin(raan_rad)
        cos_i = math.cos(math.radians(self.i))
        sin_i = math.sin(math.radians(self.i))
        cos_w = math.cos(omega_rad)
        sin_w = math.sin(omega_rad)

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
                 epoch=None,
                 j2_perturbation=True) -> "OrbitalElements":
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
            j2_perturbation=j2_perturbation,
        )


def check_visibility(sat_pos, gs_pos, min_elevation=10):
    """检查卫星与地面站的可见性（仰角 >= min_elevation）。

    已更新为调用 ``backend.physics.geometry.check_visibility_enu``，
    基于 WGS-84 ECEF 拓扑坐标精确求仰角，替代球面正弦/大圆角近似。
    对外接口与原实现保持兼容。
    """
    return check_visibility_enu(sat_pos, gs_pos, min_elevation_deg=min_elevation)


def check_geo_visibility(leo_pos, geo_pos):
    """检查 LEO 与 GEO 中继星的可见性。

    已更新为调用 ``backend.physics.geometry.check_geo_visibility_enu``，
    基于精确仰角阈值判断，替代固定 80° 地心角近似。
    """
    return check_geo_visibility_enu(leo_pos, geo_pos)


def _slant_range_km(sat_pos, target_pos) -> float:
    """计算卫星到目标点斜距 (km)，用于链路预算。

    使用球面几何近似：
        d = √((alt_sat - alt_tgt)² + (R_E·sin(angle))²)

    Parameters
    ----------
    sat_pos : dict
        卫星位置，含 lat/lon/alt (alt 单位 m)。
    target_pos : dict
        目标位置，含 lat/lon/alt (alt 单位 m)。

    Returns
    -------
    float
        斜距 (km)。
    """
    R_E = 6371.0  # km
    angle = calc_central_angle(
        sat_pos["lat"], sat_pos["lon"],
        target_pos["lat"], target_pos["lon"],
    )
    alt_sat_km = sat_pos["alt"] / 1000.0
    alt_tgt_km = target_pos.get("alt", 0.0) / 1000.0
    dist = math.sqrt(
        (alt_sat_km - alt_tgt_km) ** 2
        + (R_E * math.sin(math.radians(angle))) ** 2
    )
    return max(dist, 1.0)  # 最小 1 km，防止除零


def calculate_direct_rate(sat_pos, gs, data_type=None):
    """直连链路速率 (Mbps)，由链路预算引擎驱动（含大气衰减）。

    替代原 base_rate × exp(-d/k) 经验公式，
    使用 FSPL/EIRP/G-T/C-N0 推导物理上准确的可达速率；
    通过仰角与地面站降雨率叠加 ITU-R P.838/P.618 大气衰减。
    """
    gs_lat = gs["lat"]
    gs_lon = gs["lon"]
    gs_alt_m = gs.get("alt", 0.0)
    sat_alt_m = sat_pos.get("alt", 500e3)

    # 精确计算仰角（用于大气衰减路径折算）
    look = compute_look_angles(
        sat_lat=sat_pos["lat"],
        sat_lon=sat_pos["lon"],
        sat_alt_m=sat_alt_m,
        gs_lat=gs_lat,
        gs_lon=gs_lon,
        gs_alt_m=gs_alt_m,
    )
    elevation_deg = look["elevation_deg"]
    dist_km = look["slant_range_km"] if look["slant_range_km"] > 0 else _slant_range_km(
        sat_pos, {"lat": gs_lat, "lon": gs_lon, "alt": gs_alt_m}
    )

    antenna_type = gs.get("antenna_type", "Ka")
    # 地面站可配置降雨率场景（默认晴天）
    rainfall_rate_mm_h = gs.get("rainfall_rate_mm_h", 0.0)
    gs_altitude_km = gs_alt_m / 1000.0

    result = link_budget_direct(
        distance_km=dist_km,
        antenna_type=antenna_type,
        data_type=data_type,
        elevation_deg=elevation_deg,
        rainfall_rate_mm_h=rainfall_rate_mm_h,
        gs_altitude_km=gs_altitude_km,
    )
    return max(result.achievable_rate_mbps, 5.0)


def calculate_relay_rate(sat_pos, geo_pos, gs, data_type=None):
    """单跳中继链路速率 (Mbps)，由链路预算引擎驱动（含大气衰减）。

    分别计算 LEO→GEO 上行与 GEO→地面站下行的链路预算，
    取瓶颈（可达速率最小）链路的速率；GEO→地面站下行叠加大气衰减。
    """
    dist_leo_geo_km = _slant_range_km(sat_pos, geo_pos)

    # 计算 GEO 对地面站的仰角（用于下行大气衰减）
    gs_lat = gs["lat"]
    gs_lon = gs["lon"]
    gs_alt_m = gs.get("alt", 0.0)
    look_gs = compute_look_angles(
        sat_lat=geo_pos["lat"],
        sat_lon=geo_pos["lon"],
        sat_alt_m=geo_pos.get("alt", 35786e3),
        gs_lat=gs_lat,
        gs_lon=gs_lon,
        gs_alt_m=gs_alt_m,
    )
    elevation_deg_gs = look_gs["elevation_deg"]
    dist_geo_gs_km = look_gs["slant_range_km"] if look_gs["slant_range_km"] > 0 else _slant_range_km(
        geo_pos, {"lat": gs_lat, "lon": gs_lon, "alt": gs_alt_m}
    )

    rainfall_rate_mm_h = gs.get("rainfall_rate_mm_h", 0.0)
    gs_altitude_km = gs_alt_m / 1000.0

    result = link_budget_relay(
        dist_leo_geo_km=dist_leo_geo_km,
        dist_geo_gs_km=dist_geo_gs_km,
        data_type=data_type,
        elevation_deg_gs=elevation_deg_gs,
        rainfall_rate_mm_h=rainfall_rate_mm_h,
        gs_altitude_km=gs_altitude_km,
    )
    return max(result.achievable_rate_mbps, 5.0)


def calculate_inter_satellite_rate(geo1_pos, geo2_pos):
    """GEO 星间链路速率 (Mbps)，由链路预算引擎驱动。

    使用 60 GHz 毫米波 ISL 参数（高增益、宽带宽）。
    """
    angle = calc_central_angle(
        geo1_pos["lat"], geo1_pos["lon"],
        geo2_pos["lat"], geo2_pos["lon"],
    )
    # GEO 轨道高度约 35786 km，两颗 GEO 之间的弦长
    alt_km = geo1_pos["alt"] / 1000.0
    dist_km = 2.0 * alt_km * math.sin(math.radians(angle) / 2.0)
    dist_km = max(dist_km, 1.0)
    result = link_budget_inter_satellite(distance_km=dist_km)
    return max(result.achievable_rate_mbps, 100.0)


def calculate_multi_hop_relay_rate(sat_pos, geo1_pos, geo2_pos, gs, data_type=None):
    """多跳中继链路速率 (Mbps) - LEO→GEO1→GEO2→地面站，由链路预算引擎驱动。

    计算三段链路的链路预算，取最小值作为端到端可达速率。
    """
    # LEO → GEO1
    dist1_km = _slant_range_km(sat_pos, geo1_pos)
    res1 = link_budget_relay(dist_leo_geo_km=dist1_km, dist_geo_gs_km=dist1_km, data_type=data_type)
    rate1 = res1.achievable_rate_mbps

    # GEO1 → GEO2 (ISL)
    rate2 = calculate_inter_satellite_rate(geo1_pos, geo2_pos)

    # GEO2 → 地面站
    dist3_km = _slant_range_km(geo2_pos, {
        "lat": gs["lat"],
        "lon": gs["lon"],
        "alt": 0.0,
    })
    res3 = link_budget_direct(distance_km=dist3_km, antenna_type="Ka", data_type=data_type)
    rate3 = res3.achievable_rate_mbps

    rate = min(rate1, rate2, rate3)
    if data_type == "RAW_IMAGE":
        rate *= 0.5
    return max(rate, 5.0)
