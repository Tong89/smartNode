# -*- coding: utf-8 -*-
"""坐标系统一转换：ECI / ECEF / LLA（WGS-84 椭球）。

提供纯函数 ``eci_to_ecef`` / ``ecef_to_lla`` / ``lla_to_ecef``，替代 propagate 中把地心半径当作
球面、地球半径硬编码 6371 的简化处理。长度单位统一为千米（km），高度对外以米（m）返回。
"""
import math

# WGS-84 椭球常量
WGS84_A = 6378.137                      # 长半轴 (km)
WGS84_F = 1.0 / 298.257223563           # 扁率
WGS84_B = WGS84_A * (1.0 - WGS84_F)     # 短半轴 (km)
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)    # 第一偏心率平方

OMEGA_EARTH = 7.292115e-5               # 地球自转角速度 (rad/s)


def eci_to_ecef(x, y, z, theta):
    """ECI -> ECEF：绕地轴旋转 theta（GMST 或 ω·dt，单位弧度）。"""
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    return (x * cos_t + y * sin_t, -x * sin_t + y * cos_t, z)


def ecef_to_lla(x, y, z):
    """ECEF(km) -> (纬度°, 经度°, 高度 m)，WGS-84 椭球迭代解纬度/高度。"""
    lon = math.degrees(math.atan2(y, x))
    p = math.sqrt(x * x + y * y)
    if p < 1e-9:
        lat = 90.0 if z >= 0 else -90.0
        alt_km = abs(z) - WGS84_B
        return lat, lon, alt_km * 1000.0

    lat = math.atan2(z, p * (1.0 - WGS84_E2))  # 初值
    alt = 0.0
    for _ in range(8):
        sin_lat = math.sin(lat)
        n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
        alt = p / math.cos(lat) - n
        lat = math.atan2(z, p * (1.0 - WGS84_E2 * n / (n + alt)))

    return math.degrees(lat), lon, alt * 1000.0


def lla_to_ecef(lat_deg, lon_deg, alt_m):
    """(纬度°, 经度°, 高度 m) -> ECEF(km)。"""
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    alt_km = alt_m / 1000.0
    sin_lat = math.sin(lat)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * sin_lat * sin_lat)
    x = (n + alt_km) * math.cos(lat) * math.cos(lon)
    y = (n + alt_km) * math.cos(lat) * math.sin(lon)
    z = (n * (1.0 - WGS84_E2) + alt_km) * sin_lat
    return x, y, z
