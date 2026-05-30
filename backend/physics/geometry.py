# -*- coding: utf-8 -*-
"""精确仰角/方位角/斜距与多普勒频移计算（基于 ECEF 拓扑坐标）。

本模块实现基于站心（ENU）拓扑坐标的精确几何量：
  - ``enu_from_ecef``: 将 ECEF 差矢量转换到接收站 ENU 框架
  - ``compute_look_angles``: 精确仰角（elevation）、方位角（azimuth）与斜距（slant_range）
  - ``compute_doppler_shift``: 基于卫星 ECEF 速度矢量在视线方向投影计算多普勒频移
  - ``check_visibility_enu``: 基于真实仰角阈值的可见性判断（替换中心角近似）
  - ``check_geo_visibility_enu``: 精确 LEO-GEO 可见性（基于最小仰角而非固定 80° 中心角）

坐标约定
---------
  - 所有 ECEF 长度单位：千米（km）
  - 卫星高度（alt）字段：米（m），地面站高度如缺省按 0 m 处理
  - 速度矢量（vx, vy, vz）单位：km/s
  - 频率（carrier_freq_hz）：Hz；多普勒频移返回 Hz（正值 = 接近，负值 = 远离）

使用示例
---------
>>> from backend.physics.geometry import compute_look_angles, compute_doppler_shift
>>> # 500 km 轨道高度卫星正上方情况
>>> result = compute_look_angles(
...     sat_lat=35.0, sat_lon=116.0, sat_alt_m=500000.0,
...     gs_lat=35.0, gs_lon=116.0, gs_alt_m=0.0,
... )
>>> result["elevation_deg"]   # ≈ 90.0
>>> result["slant_range_km"]  # ≈ 500.0

依赖
----
  ``backend.physics.coordinates`` — lla_to_ecef（WGS-84 精确坐标变换）
"""
import math
from typing import Dict, Optional, Tuple

from backend.physics.coordinates import lla_to_ecef

# 光速（km/s）
SPEED_OF_LIGHT_KM_S = 299792.458


# ---------------------------------------------------------------------------
# 低级工具函数
# ---------------------------------------------------------------------------

def enu_from_ecef(
    dx: float, dy: float, dz: float,
    gs_lat_rad: float, gs_lon_rad: float,
) -> Tuple[float, float, float]:
    """将以地面站为原点的 ECEF 差矢量投影到 ENU 框架。

    参数
    ----
    dx, dy, dz : float
        ECEF 差矢量各分量（km），定义为 sat_ecef - gs_ecef。
    gs_lat_rad : float
        地面站大地纬度（弧度）。
    gs_lon_rad : float
        地面站经度（弧度）。

    返回
    ----
    (east, north, up) : Tuple[float, float, float]
        站心 ENU 分量（km）。
    """
    sin_lat = math.sin(gs_lat_rad)
    cos_lat = math.cos(gs_lat_rad)
    sin_lon = math.sin(gs_lon_rad)
    cos_lon = math.cos(gs_lon_rad)

    # ENU 旋转矩阵行向量
    east  = -sin_lon * dx + cos_lon * dy
    north = -sin_lat * cos_lon * dx - sin_lat * sin_lon * dy + cos_lat * dz
    up    =  cos_lat * cos_lon * dx + cos_lat * sin_lon * dy + sin_lat * dz

    return east, north, up


# ---------------------------------------------------------------------------
# 主要公开接口
# ---------------------------------------------------------------------------

def compute_look_angles(
    sat_lat: float,
    sat_lon: float,
    sat_alt_m: float,
    gs_lat: float,
    gs_lon: float,
    gs_alt_m: float = 0.0,
) -> Dict[str, float]:
    """计算卫星相对于地面站的精确仰角、方位角与斜距。

    基于 WGS-84 椭球将双方位置转换至 ECEF，再投影到地面站 ENU 拓扑坐标框架。

    参数
    ----
    sat_lat, sat_lon : float
        卫星大地纬度、经度（度）。
    sat_alt_m : float
        卫星高度（米）。
    gs_lat, gs_lon : float
        地面站大地纬度、经度（度）。
    gs_alt_m : float
        地面站高度（米），默认 0 m（海平面）。

    返回
    ----
    dict
        ``elevation_deg``  — 仰角（度），范围 [-90, 90]
        ``azimuth_deg``    — 方位角（度），北偏东，范围 [0, 360)
        ``slant_range_km`` — 斜距（千米），非负值
    """
    # ECEF 坐标（km）
    sx, sy, sz = lla_to_ecef(sat_lat, sat_lon, sat_alt_m)
    gx, gy, gz = lla_to_ecef(gs_lat, gs_lon, gs_alt_m)

    dx, dy, dz = sx - gx, sy - gy, sz - gz

    gs_lat_rad = math.radians(gs_lat)
    gs_lon_rad = math.radians(gs_lon)

    east, north, up = enu_from_ecef(dx, dy, dz, gs_lat_rad, gs_lon_rad)

    slant_range_km = math.sqrt(east * east + north * north + up * up)

    if slant_range_km < 1e-9:
        # 卫星与地面站几乎重合
        return {"elevation_deg": 90.0, "azimuth_deg": 0.0, "slant_range_km": 0.0}

    horizontal_range = math.sqrt(east * east + north * north)

    # 正上方或正下方特殊情形：水平分量极小时直接给精确仰角
    if horizontal_range < slant_range_km * 1e-9:
        elevation_deg = 90.0 if up >= 0 else -90.0
    else:
        elevation_rad = math.atan2(up, horizontal_range)
        elevation_deg = math.degrees(elevation_rad)
        # 数值误差夹紧：避免超出 ±90° 范围
        elevation_deg = max(-90.0, min(90.0, elevation_deg))

    # 方位角：北偏东，atan2(east, north)
    azimuth_rad = math.atan2(east, north)
    azimuth_deg = math.degrees(azimuth_rad) % 360.0

    return {
        "elevation_deg": elevation_deg,
        "azimuth_deg": azimuth_deg,
        "slant_range_km": slant_range_km,
    }


def compute_doppler_shift(
    sat_lat: float,
    sat_lon: float,
    sat_alt_m: float,
    sat_vx_km_s: float,
    sat_vy_km_s: float,
    sat_vz_km_s: float,
    gs_lat: float,
    gs_lon: float,
    gs_alt_m: float = 0.0,
    carrier_freq_hz: float = 20.2e9,
) -> Dict[str, float]:
    """计算卫星与地面站之间的多普勒频移。

    多普勒频移由卫星 ECEF 速度矢量在视线方向（地面站 → 卫星）上的投影确定：
        Δf = f₀ × (−v_r) / c
    其中 v_r 为径向速度分量，约定朝向地面站（接近）为正，远离为负；
    因此频移符号：接近 → Δf > 0（蓝移），远离 → Δf < 0（红移）。

    参数
    ----
    sat_lat, sat_lon : float
        卫星大地纬度、经度（度）。
    sat_alt_m : float
        卫星高度（米）。
    sat_vx_km_s, sat_vy_km_s, sat_vz_km_s : float
        卫星 ECEF 速度矢量各分量（km/s）。
    gs_lat, gs_lon : float
        地面站大地纬度、经度（度）。
    gs_alt_m : float
        地面站高度（米），默认 0 m。
    carrier_freq_hz : float
        载波频率（Hz），默认 Ka 波段 20.2 GHz。

    返回
    ----
    dict
        ``doppler_hz``      — 多普勒频移（Hz），正 = 接近（蓝移），负 = 远离（红移）
        ``radial_vel_km_s`` — 径向速度（km/s），正 = 接近地面站
        ``slant_range_km``  — 斜距（千米）
    """
    # ECEF 坐标（km）
    sx, sy, sz = lla_to_ecef(sat_lat, sat_lon, sat_alt_m)
    gx, gy, gz = lla_to_ecef(gs_lat, gs_lon, gs_alt_m)

    dx, dy, dz = sx - gx, sy - gy, sz - gz
    slant_range_km = math.sqrt(dx * dx + dy * dy + dz * dz)

    if slant_range_km < 1e-9:
        return {"doppler_hz": 0.0, "radial_vel_km_s": 0.0, "slant_range_km": 0.0}

    # 单位视线向量：从地面站指向卫星
    ux, uy, uz = dx / slant_range_km, dy / slant_range_km, dz / slant_range_km

    # 卫星速度在视线方向上的投影（正 = 远离地面站）
    v_radial_away = sat_vx_km_s * ux + sat_vy_km_s * uy + sat_vz_km_s * uz

    # 接近速度（正 = 接近）
    radial_vel_km_s = -v_radial_away

    # 多普勒频移：接近为正（蓝移）
    doppler_hz = carrier_freq_hz * radial_vel_km_s / SPEED_OF_LIGHT_KM_S

    return {
        "doppler_hz": doppler_hz,
        "radial_vel_km_s": radial_vel_km_s,
        "slant_range_km": slant_range_km,
    }


def check_visibility_enu(
    sat_pos: Dict[str, float],
    gs_pos: Dict[str, float],
    min_elevation_deg: float = 10.0,
) -> bool:
    """基于精确 ENU 拓扑坐标判断卫星可见性。

    替换 ``orbit.check_visibility`` 中的大圆中心角近似，改用 WGS-84 ECEF
    拓扑坐标精确求仰角，可见性判据改为基于真实仰角阈值。

    参数
    ----
    sat_pos : dict
        卫星位置，须含 ``lat``（度）、``lon``（度）、``alt``（米）。
    gs_pos : dict
        地面站位置，须含 ``lat``（度）、``lon``（度）；
        可选 ``alt``（米），缺省按 0 m 处理。
    min_elevation_deg : float
        最小仰角阈值（度），默认 10°。

    返回
    ----
    bool
        仰角 >= min_elevation_deg 则为 True，否则 False。
    """
    gs_alt = gs_pos.get("alt", 0.0)
    result = compute_look_angles(
        sat_lat=sat_pos["lat"],
        sat_lon=sat_pos["lon"],
        sat_alt_m=sat_pos["alt"],
        gs_lat=gs_pos["lat"],
        gs_lon=gs_pos["lon"],
        gs_alt_m=gs_alt,
    )
    return result["elevation_deg"] >= min_elevation_deg


def check_geo_visibility_enu(
    leo_pos: Dict[str, float],
    geo_pos: Dict[str, float],
    min_elevation_deg: float = 0.0,
) -> bool:
    """精确 LEO-GEO 可见性判断（卫星间连通性）。

    从 LEO 卫星视角判断 GEO 卫星是否在地平线以上（即两星之间的连线不被地球遮挡）。
    原 ``orbit.check_geo_visibility`` 使用固定 80° 地心角阈值，本函数改用
    真实仰角阈值：以 LEO 为"观测站"，检查 GEO 的仰角是否高于 min_elevation_deg。

    当两星地心角约 80° 时，GEO 仰角约 0°（恰好在 LEO 地平线上），因此默认阈值
    设为 0°，与原 80° 地心角判据近似等效。

    参数
    ----
    leo_pos : dict
        LEO 卫星位置，含 ``lat``、``lon``（度）、``alt``（米）。
    geo_pos : dict
        GEO 卫星位置，含 ``lat``、``lon``（度）、``alt``（米）。
    min_elevation_deg : float
        GEO 在 LEO 视角下的最小仰角（度），默认 0°。

    返回
    ----
    bool
        GEO 仰角 >= min_elevation_deg 则为 True（两星连线不被地球遮挡）。
    """
    # 以 LEO 为观测点（当作地面站），求 GEO ���仰角
    result = compute_look_angles(
        sat_lat=geo_pos["lat"],
        sat_lon=geo_pos["lon"],
        sat_alt_m=geo_pos["alt"],
        gs_lat=leo_pos["lat"],
        gs_lon=leo_pos["lon"],
        gs_alt_m=leo_pos["alt"],
    )
    return result["elevation_deg"] >= min_elevation_deg
