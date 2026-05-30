# -*- coding: utf-8 -*-
"""
天基智枢 SmartNode 仿真平台
仿真核心模块
"""
import math
import time
import random
import threading
import os
import sys
import logging
from datetime import datetime, timedelta

from backend.config import (
    HANDOVER_RATE_RATIO,
    RESOURCE_TIGHT_THRESHOLD as CFG_RESOURCE_TIGHT_THRESHOLD,
)

logger = logging.getLogger("smartnode")

# ==========================================
# 0.5 Open API mode
# ==========================================
# 认证与角色权限逻辑已移除。前端可直接调用本地仿真 API，
# 便于开源部署和前后端分离运行。

# ==========================================
# 0. 核心算法库
# ==========================================
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def calc_central_angle(lat1, lon1, lat2, lon2):
    """计算球面大圆地心角 (Degrees)"""
    rad = math.pi / 180.0
    phi1, phi2 = lat1 * rad, lat2 * rad
    dphi = (lat2 - lat1) * rad
    dlam = (lon2 - lon1) * rad
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return c * 180.0 / math.pi


# ==========================================
# 1. 中国境内地面站配置 (50个固定站点)
# ==========================================
CHINA_GROUND_STATIONS = [
    # 东北地区
    {"id": "GS_001", "name": "哈尔滨站", "lat": 45.75, "lon": 126.65, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_002", "name": "长春站", "lat": 43.88, "lon": 125.32, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_003", "name": "沈阳站", "lat": 41.80, "lon": 123.43, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_004", "name": "大连站", "lat": 38.91, "lon": 121.62, "antenna_type": "Ka", "max_links": 1},
    {"id": "GS_005", "name": "齐齐哈尔站", "lat": 47.35, "lon": 123.92, "antenna_type": "X", "max_links": 1},
    # 华北地区
    {"id": "GS_006", "name": "北京站", "lat": 39.90, "lon": 116.40, "antenna_type": "Ka", "max_links": 4},
    {"id": "GS_007", "name": "天津站", "lat": 39.13, "lon": 117.20, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_008", "name": "石家庄站", "lat": 38.04, "lon": 114.48, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_009", "name": "太原站", "lat": 37.87, "lon": 112.55, "antenna_type": "X", "max_links": 2},
    {"id": "GS_010", "name": "呼和浩特站", "lat": 40.84, "lon": 111.75, "antenna_type": "X", "max_links": 1},
    # 华东地区
    {"id": "GS_011", "name": "上海站", "lat": 31.23, "lon": 121.47, "antenna_type": "Ka", "max_links": 4},
    {"id": "GS_012", "name": "南京站", "lat": 32.06, "lon": 118.80, "antenna_type": "Ka", "max_links": 3},
    {"id": "GS_013", "name": "杭州站", "lat": 30.27, "lon": 120.15, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_014", "name": "合肥站", "lat": 31.82, "lon": 117.23, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_015", "name": "济南站", "lat": 36.67, "lon": 116.98, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_016", "name": "青岛站", "lat": 36.07, "lon": 120.38, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_017", "name": "福州站", "lat": 26.07, "lon": 119.30, "antenna_type": "X", "max_links": 2},
    {"id": "GS_018", "name": "厦门站", "lat": 24.48, "lon": 118.09, "antenna_type": "X", "max_links": 1},
    {"id": "GS_019", "name": "南昌站", "lat": 28.68, "lon": 115.86, "antenna_type": "X", "max_links": 1},
    {"id": "GS_020", "name": "宁波站", "lat": 29.87, "lon": 121.55, "antenna_type": "X", "max_links": 1},
    # 华中地区
    {"id": "GS_021", "name": "武汉站", "lat": 30.58, "lon": 114.27, "antenna_type": "Ka", "max_links": 3},
    {"id": "GS_022", "name": "长沙站", "lat": 28.23, "lon": 112.94, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_023", "name": "郑州站", "lat": 34.76, "lon": 113.65, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_024", "name": "洛阳站", "lat": 34.62, "lon": 112.45, "antenna_type": "X", "max_links": 1},
    {"id": "GS_025", "name": "襄阳站", "lat": 32.01, "lon": 112.14, "antenna_type": "X", "max_links": 1},
    # 华南地区
    {"id": "GS_026", "name": "广州站", "lat": 23.13, "lon": 113.26, "antenna_type": "Ka", "max_links": 3},
    {"id": "GS_027", "name": "深圳站", "lat": 22.54, "lon": 114.06, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_028", "name": "南宁站", "lat": 22.82, "lon": 108.32, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_029", "name": "海口站", "lat": 20.04, "lon": 110.20, "antenna_type": "X", "max_links": 2},
    {"id": "GS_030", "name": "三亚站", "lat": 18.0, "lon": 109.0, "antenna_type": "Ka", "max_links": 2},
    # 西南地区
    {"id": "GS_031", "name": "成都站", "lat": 30.57, "lon": 104.07, "antenna_type": "Ka", "max_links": 3},
    {"id": "GS_032", "name": "重庆站", "lat": 29.56, "lon": 106.55, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_033", "name": "昆明站", "lat": 25.04, "lon": 102.71, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_034", "name": "贵阳站", "lat": 26.58, "lon": 106.72, "antenna_type": "X", "max_links": 2},
    {"id": "GS_035", "name": "拉萨站", "lat": 29.65, "lon": 91.13, "antenna_type": "X", "max_links": 1},
    {"id": "GS_036", "name": "西昌站", "lat": 27.90, "lon": 102.26, "antenna_type": "Ka", "max_links": 2},
    # 西北地区
    {"id": "GS_037", "name": "西安站", "lat": 34.27, "lon": 108.95, "antenna_type": "Ka", "max_links": 3},
    {"id": "GS_038", "name": "兰州站", "lat": 36.06, "lon": 103.83, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_039", "name": "乌鲁木齐站", "lat": 43.82, "lon": 87.62, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_040", "name": "银川站", "lat": 38.49, "lon": 106.23, "antenna_type": "X", "max_links": 1},
    {"id": "GS_041", "name": "西宁站", "lat": 36.62, "lon": 101.78, "antenna_type": "X", "max_links": 1},
    {"id": "GS_042", "name": "喀什站", "lat": 39.0, "lon": 76.0, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_043", "name": "酒泉站", "lat": 39.74, "lon": 98.49, "antenna_type": "Ka", "max_links": 2},
    # 特殊/边远站点
    {"id": "GS_044", "name": "漠河站", "lat": 52.97, "lon": 122.53, "antenna_type": "X", "max_links": 1},
    {"id": "GS_045", "name": "满洲里站", "lat": 49.60, "lon": 117.45, "antenna_type": "X", "max_links": 1},
    {"id": "GS_046", "name": "佳木斯站", "lat": 46.0, "lon": 130.0, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_047", "name": "丹东站", "lat": 40.00, "lon": 124.38, "antenna_type": "X", "max_links": 1},
    {"id": "GS_048", "name": "延吉站", "lat": 42.89, "lon": 129.51, "antenna_type": "X", "max_links": 1},
    {"id": "GS_049", "name": "文昌站", "lat": 19.61, "lon": 110.75, "antenna_type": "Ka", "max_links": 2},
    {"id": "GS_050", "name": "珠海站", "lat": 22.27, "lon": 113.58, "antenna_type": "X", "max_links": 1},
]


# ==========================================
# 2. 卫星轨道配置 (轨道六根数)
# ==========================================
class OrbitalElements:
    """轨道六根数定义 - 用于精确计算卫星位置"""

    def __init__(self, name, sat_id,
                 semi_major_axis,  # 半长轴 (km)
                 eccentricity,  # 偏心率
                 inclination,  # 轨道倾角 (度)
                 raan,  # 升交点赤经 (度)
                 arg_perigee,  # 近地点幅角 (度)
                 mean_anomaly,  # 平近点角 (度)
                 epoch=None):  # 历元时间
        self.name = name
        self.sat_id = sat_id
        self.a = semi_major_axis
        self.e = eccentricity
        self.i = inclination
        self.raan = raan
        self.omega = arg_perigee
        self.M0 = mean_anomaly
        self.epoch = epoch or datetime.now()

        # 地球引力常数 (km³/s²)
        self.mu = 398600.4418
        # 地球半径 (km)
        self.R_earth = 6371.0

    def get_mean_motion(self):
        """计算平均角速度 (rad/s)"""
        return math.sqrt(self.mu / (self.a ** 3))

    def get_orbital_period(self):
        """计算轨道周期 (秒)"""
        return 2 * math.pi * math.sqrt((self.a ** 3) / self.mu)

    def get_altitude(self):
        """获取轨道高度 (米)"""
        return (self.a - self.R_earth) * 1000

    def propagate(self, current_time):
        """
        根据当前时间计算卫星位置 (简化的二体问题)
        参数: current_time - 秒数或datetime对象
        返回: (lat, lon, alt) 纬度(度), 经度(度), 高度(米)
        """
        if isinstance(current_time, datetime):
            dt_seconds = (current_time - self.epoch).total_seconds()
        else:
            dt_seconds = current_time

        # 计算当前平近点角
        n = self.get_mean_motion()
        M = math.radians(self.M0) + n * dt_seconds
        M = M % (2 * math.pi)

        # 解开普勒方程 (迭代法求偏近点角E)
        E = M
        for _ in range(10):
            E = M + self.e * math.sin(E)

        # 计算真近点角
        nu = 2 * math.atan2(
            math.sqrt(1 + self.e) * math.sin(E / 2),
            math.sqrt(1 - self.e) * math.cos(E / 2)
        )

        # 计算轨道面内坐标
        r = self.a * (1 - self.e * math.cos(E))

        # 轨道面内位置
        x_orb = r * math.cos(nu)
        y_orb = r * math.sin(nu)

        # 转换到地心惯性坐标系
        cos_O = math.cos(math.radians(self.raan))
        sin_O = math.sin(math.radians(self.raan))
        cos_i = math.cos(math.radians(self.i))
        sin_i = math.sin(math.radians(self.i))
        cos_w = math.cos(math.radians(self.omega))
        sin_w = math.sin(math.radians(self.omega))

        # 地心惯性坐标 (ECI)
        x = (cos_O * cos_w - sin_O * sin_w * cos_i) * x_orb + \
            (-cos_O * sin_w - sin_O * cos_w * cos_i) * y_orb
        y = (sin_O * cos_w + cos_O * sin_w * cos_i) * x_orb + \
            (-sin_O * sin_w + cos_O * cos_w * cos_i) * y_orb
        z = (sin_w * sin_i) * x_orb + (cos_w * sin_i) * y_orb

        # 地球自转修正 (地球自转角速度 7.292115e-5 rad/s)
        omega_earth = 7.292115e-5
        theta = omega_earth * dt_seconds

        # 转到地固坐标系 (ECEF)
        x_ecef = x * math.cos(theta) + y * math.sin(theta)
        y_ecef = -x * math.sin(theta) + y * math.cos(theta)
        z_ecef = z

        # 转换到经纬度
        r_ground = math.sqrt(x_ecef ** 2 + y_ecef ** 2 + z_ecef ** 2)
        lat = math.degrees(math.asin(z_ecef / r_ground))
        lon = math.degrees(math.atan2(y_ecef, x_ecef))
        alt = (r_ground - self.R_earth) * 1000  # 转换为米

        return lat, lon, alt


# ==========================================
# 2.3 LEO卫星天线配置 ⭐ 新增
# ==========================================
LEO_ANTENNA_CONFIG = {
    "ground_antenna": {          # 对地天线（下行数据传输）
        "type": "X-band",
        "frequency": "8-12 GHz",
        "gain": 35,              # dBi
        "beam_width": 2.0,       # 波束宽度（度）
        "max_data_rate": 150,    # Mbps
        "max_links": 2,          # 最大同时链路数
        "polarization": "RHCP",  # 右旋圆极化
        "pointing_accuracy": 0.1 # 指向精度（度）
    },
    "relay_antenna": {           # 对中继天线（星间链路）
        "type": "Ka-band",
        "frequency": "26.5-40 GHz",
        "gain": 40,              # dBi
        "beam_width": 0.5,       # 波束宽度（度）
        "max_data_rate": 300,    # Mbps
        "max_links": 1,          # 最大同时链路数
        "polarization": "dual",  # 双极化
        "pointing_accuracy": 0.05 # 指向精度（度）
    },
    "command_antenna": {         # 指令接收天线（上行）
        "type": "S-band",
        "frequency": "2-4 GHz",
        "gain": 10,              # dBi
        "beam_width": 80,        # 全向覆盖
        "sensitivity": -120      # dBm
    }
}

# 预定义的低轨卫星星座（减少到8颗以提高性能）
# ⭐ 每颗卫星都具备上述三种天线配置
LEO_SATELLITES = [
    OrbitalElements("遥感一号", "LEO_001", 6871, 0.001, 97.4, 0, 0, 0),
    OrbitalElements("遥感二号", "LEO_002", 6871, 0.001, 97.4, 45, 0, 90),
    OrbitalElements("遥感三号", "LEO_003", 6871, 0.001, 97.4, 90, 0, 180),
    OrbitalElements("遥感四号", "LEO_004", 6871, 0.001, 97.4, 135, 0, 270),
    OrbitalElements("光学遥感一号", "LEO_006", 6771, 0.001, 63.4, 30, 0, 120),
    OrbitalElements("光学遥感二号", "LEO_007", 6771, 0.001, 63.4, 75, 0, 210),
    OrbitalElements("SAR卫星一号", "LEO_008", 6921, 0.001, 98.2, 120, 0, 60),
    OrbitalElements("SAR卫星二号", "LEO_009", 6921, 0.001, 98.2, 165, 0, 150),
]

# 预定义的中轨卫星星座（禁用MEO以提高性能）
MEO_SATELLITES = [
    # 注释掉MEO卫星以提高性能
    # OrbitalElements("导航一号", "MEO_001", 21528, 0.01, 55.0, 0, 0, 0),
]

# 中继星 (GEO) 配置 - 均匀分布在120-140度之间
# ⭐ 增强配置：详细天线参数、波束角、可视性特性
GEO_RELAY_SATELLITES = [
    {
        "id": "GEO_001", 
        "name": "天链二号-01", 
        "lon": 80.0,  # 修改为80度
        "antenna": {
            "type": "Ka",                    # 天线类型
            "frequency": "26.5-40 GHz",      # 频率范围
            "beam_width": 0.5,               # 波束宽度（度）⭐
            "beam_count": 4,                 # 波束数量
            "beam_gain": 50,                 # 波束增益（dBi）
            "beam_steering": "electronic",   # 波束控制方式：电子扫描
            "polarization": "dual",          # 极化方式：双极化
            "scan_range": {                  # 扫描范围⭐
                "azimuth": (-60, 60),        # 方位角范围（度）
                "elevation": (10, 90)        # 仰角范围（度）
            }
        },
        "beams": [                           # 每个波束单独建模⭐
            {"id": "B1", "azimuth": 0, "elevation": 45, "status": "free", "target": None},
            {"id": "B2", "azimuth": 30, "elevation": 45, "status": "free", "target": None},
            {"id": "B3", "azimuth": -30, "elevation": 45, "status": "free", "target": None},
            {"id": "B4", "azimuth": 0, "elevation": 70, "status": "free", "target": None}
        ],
        "bandwidth": 1600,                   # 总带宽（Mbps）
        "coverage": {                        # 覆盖特性⭐
            "fov": 120,                      # 视场角（度）
            "min_elevation": 10,             # 最小仰角（度）
            "visibility_range": "全球约1/3"   # 可视范围描述
        }
    },
    {
        "id": "GEO_002", 
        "name": "天链二号-02", 
        "lon": 171.0,  # 修改为171度
        "antenna": {
            "type": "Ka",
            "frequency": "26.5-40 GHz",
            "beam_width": 0.5,               # ⭐ 波束角
            "beam_count": 4,
            "beam_gain": 50,
            "beam_steering": "electronic",
            "polarization": "dual",
            "scan_range": {
                "azimuth": (-60, 60),
                "elevation": (10, 90)
            }
        },
        "beams": [
            {"id": "B1", "azimuth": 0, "elevation": 45, "status": "free", "target": None},
            {"id": "B2", "azimuth": 30, "elevation": 45, "status": "free", "target": None},
            {"id": "B3", "azimuth": -30, "elevation": 45, "status": "free", "target": None},
            {"id": "B4", "azimuth": 0, "elevation": 70, "status": "free", "target": None}
        ],
        "bandwidth": 1600,
        "coverage": {
            "fov": 120,
            "min_elevation": 10,
            "visibility_range": "全球约1/3"
        }
    },
    {
        "id": "GEO_003", 
        "name": "天链二号-03", 
        "lon": 10.5,  # 修改为10.5度
        "antenna": {
            "type": "Ka",
            "frequency": "26.5-40 GHz",
            "beam_width": 0.5,               # ⭐ 波束角
            "beam_count": 4,
            "beam_gain": 50,
            "beam_steering": "electronic",
            "polarization": "dual",
            "scan_range": {
                "azimuth": (-60, 60),
                "elevation": (10, 90)
            }
        },
        "beams": [
            {"id": "B1", "azimuth": 0, "elevation": 45, "status": "free", "target": None},
            {"id": "B2", "azimuth": 30, "elevation": 45, "status": "free", "target": None},
            {"id": "B3", "azimuth": -30, "elevation": 45, "status": "free", "target": None},
            {"id": "B4", "azimuth": 0, "elevation": 70, "status": "free", "target": None}
        ],
        "bandwidth": 1600,
        "coverage": {
            "fov": 120,
            "min_elevation": 10,
            "visibility_range": "全球约1/3"
        }
    }
]

# 中继星专用地面站配置（佳木斯、三亚、喀什）
GEO_RELAY_GROUND_STATIONS = [
    {"id": "GS_046", "name": "佳木斯站", "lat": 46.0, "lon": 130.0, "antenna_type": "Ka", "max_links": 4, "relay_support": True},
    {"id": "GS_030", "name": "三亚站", "lat": 18.0, "lon": 109.0, "antenna_type": "Ka", "max_links": 4, "relay_support": True},
    {"id": "GS_042", "name": "喀什站", "lat": 39.0, "lon": 76.0, "antenna_type": "Ka", "max_links": 4, "relay_support": True},
]


# ==========================================
# 2.4 天地基随遇接入通信资源配置（相控阵）
# ==========================================
OPPORTUNISTIC_STATIONS = [
    {
        "id": "OPP_001",
        "name": "移动接入站001",
        "lat": 30.5,
        "lon": 114.3,
        "type": "mobile",
        # 相控阵天线特性
        "phased_array": {
            "elements": 256,              # 阵元数量
            "element_spacing": 0.5,       # 阵元间距（波长）
            "beam_forming": "digital",    # 数字波束成形
            "scan_range": {               # 扫描范围
                "azimuth": (-60, 60),     # 方位角（度）
                "elevation": (10, 90)     # 仰角（度）
            },
            "scan_speed": 0.1,            # 扫描速度（度/ms）
            "pointing_accuracy": 0.05     # 指向精度（度）
        },
        # 波束管理
        "beam_management": {
            "max_beams": 16,              # 最大同时波束数
            "beam_width": 2.0,            # 单波束宽度（度）
            "beam_allocation": "dynamic", # 动态分配
            "interference_suppression": True,  # 干扰抑制
            "nulling_depth": -40          # 零陷深度（dB）
        },
        # 多路接收支持
        "multi_channel": {
            "channels": 8,                # 接收通道数
            "bandwidth_per_channel": 500, # MHz
            "total_bandwidth": 4000,      # MHz
            "modulation": ["QPSK", "8PSK", "16APSK"],  # 支持的调制方式
            "parallel_decode": True       # 并行解码
        },
        # 上行链路配置
        "uplink": {
            "frequency": "27.5-31 GHz",   # Ka上行
            "power": 100,                 # W
            "eirp": 75,                   # dBW
            "modulation": "16APSK"
        },
        # 下行链路配置
        "downlink": {
            "frequency": "17.7-21.2 GHz", # Ka下行
            "sensitivity": -110,          # dBm
            "g_t": 30,                    # dB/K
            "demodulation": ["QPSK", "8PSK", "16APSK"]
        },
        # 当前状态
        "current_beams": [],              # 当前使用的波束
        "available_channels": 8           # 可用通道数
    },
    {
        "id": "OPP_002",
        "name": "移动接入站002",
        "lat": 39.9,
        "lon": 116.4,
        "type": "mobile",
        "phased_array": {
            "elements": 256,
            "element_spacing": 0.5,
            "beam_forming": "digital",
            "scan_range": {
                "azimuth": (-60, 60),
                "elevation": (10, 90)
            },
            "scan_speed": 0.1,
            "pointing_accuracy": 0.05
        },
        "beam_management": {
            "max_beams": 16,
            "beam_width": 2.0,
            "beam_allocation": "dynamic",
            "interference_suppression": True,
            "nulling_depth": -40
        },
        "multi_channel": {
            "channels": 8,
            "bandwidth_per_channel": 500,
            "total_bandwidth": 4000,
            "modulation": ["QPSK", "8PSK", "16APSK"],
            "parallel_decode": True
        },
        "uplink": {
            "frequency": "27.5-31 GHz",
            "power": 100,
            "eirp": 75,
            "modulation": "16APSK"
        },
        "downlink": {
            "frequency": "17.7-21.2 GHz",
            "sensitivity": -110,
            "g_t": 30,
            "demodulation": ["QPSK", "8PSK", "16APSK"]
        },
        "current_beams": [],
        "available_channels": 8
    },
    {
        "id": "OPP_003",
        "name": "移动接入站003",
        "lat": 31.2,
        "lon": 121.5,
        "type": "mobile",
        "phased_array": {
            "elements": 256,
            "element_spacing": 0.5,
            "beam_forming": "digital",
            "scan_range": {
                "azimuth": (-60, 60),
                "elevation": (10, 90)
            },
            "scan_speed": 0.1,
            "pointing_accuracy": 0.05
        },
        "beam_management": {
            "max_beams": 16,
            "beam_width": 2.0,
            "beam_allocation": "dynamic",
            "interference_suppression": True,
            "nulling_depth": -40
        },
        "multi_channel": {
            "channels": 8,
            "bandwidth_per_channel": 500,
            "total_bandwidth": 4000,
            "modulation": ["QPSK", "8PSK", "16APSK"],
            "parallel_decode": True
        },
        "uplink": {
            "frequency": "27.5-31 GHz",
            "power": 100,
            "eirp": 75,
            "modulation": "16APSK"
        },
        "downlink": {
            "frequency": "17.7-21.2 GHz",
            "sensitivity": -110,
            "g_t": 30,
            "demodulation": ["QPSK", "8PSK", "16APSK"]
        },
        "current_beams": [],
        "available_channels": 8
    }
]


# ==========================================
# 2.5 数据类型配置 (4种数据类型) ⭐ 已精简
# ==========================================
# ⭐ 等待时限定义（原"最大延迟"）：
# - 等待时限：请求提交后，系统在此时间内必须完成任务调度（分配传输资源）
# - 超时处理：超过等待时限仍未安排传输的请求，需用户重新提交申请
# - 回传定义：数据从卫星传输到地面站的完整过程，包括直连和中继两种方式
# - 时延组成：等待时延（排队+调度）+ 传输时延（实际数据传输时间）
MAX_WAIT_LIMIT = 1800  # 等待时限30分钟（1800秒）

DATA_TYPES = {
    "TASK_CMD": {
        "name": "任务指令",
        "size_range": (10, 100),  # ⭐ 增大数据量，让传输更久
        "size_unit": "KB",
        "priority_range": (8, 10),
        "max_wait_limit": MAX_WAIT_LIMIT,
        "allowed_links": ["relay"],  # 只用中继
        "beta": 0.5,
        "base_value": 150.0,
        "immediate": True
    },
    "INTEL": {
        "name": "情报信息",
        "size_range": (500, 5000),  # ⭐ 增大数据量，让传输更久
        "size_unit": "KB",
        "priority_range": (7, 10),
        "max_wait_limit": MAX_WAIT_LIMIT,
        "allowed_links": ["relay"],  # 只用中继
        "beta": 0.2,
        "base_value": 120.0,
        "immediate": True
    },
    "DATA_SLICE": {
        "name": "数据切片",
        "size_range": (50, 500),  # ⭐ 增大最小值，让传输更久
        "size_unit": "MB",
        "priority_range": (3, 7),
        "max_wait_limit": MAX_WAIT_LIMIT,
        "allowed_links": ["direct", "relay"],
        "beta": 0.05,
        "base_value": 80.0
    },
    "RAW_IMAGE": {
        "name": "原始影像",
        "size_range": (2, 10),  # ⭐ 增大最小值
        "size_unit": "GB",
        "priority_range": (1, 5),
        "max_wait_limit": MAX_WAIT_LIMIT,
        "allowed_links": ["direct"],
        "beta": 0.01,
        "base_value": 40.0
    }
}

# ==========================================
# 2.6 标准化拒绝原因 ⭐ 优化
# ==========================================
REJECTION_REASONS = {
    # 资源类
    "NO_VISIBLE_GS": "当前无可见地面站",
    "NO_VISIBLE_RELAY": "当前无可用中继链路", 
    "RESOURCE_BUSY": "所需资源正被占用",
    "BANDWIDTH_EXCEEDED": "中继带宽不足",
    "SATELLITE_OVERLOAD": "卫星任务队列已满",
    
    # 超时类
    "TIMEOUT_WAIT": "等待超时（超过30分钟未开始传输，请重新提交）",
    "TIMEOUT_TRANSMISSION": "传输超时（传输过程异常中断）",
    
    # 链路类
    "LINK_INTERRUPTED": "传输链路意外中断",
    "RAW_IMAGE_NO_DIRECT": "原始影像仅支持直连地面站传输",
    
    # 系统类
    "SATELLITE_REMOVED": "分配的卫星已从系统移除",
    "TIME_WINDOW_INVALID": "指定的时间窗口无效",
    "TIME_WINDOW_CONFLICT": "指定时间段与其他任务冲突"
}

# ==========================================
# 数据组合维度配置（扩展到50+种）
# ==========================================
DATA_URGENCY_LEVELS = ["immediate", "urgent", "normal", "low"]
DATA_QOS_LEVELS = ["high", "medium", "low"]
DATA_SECURITY_LEVELS = ["top_secret", "secret", "confidential", "public"]

# 数据组合表（4类型 × 4紧急度 × 3QoS × 部分安全级别 = 40+种）
DATA_COMBINATIONS = []

# 生成组合配置
for data_type, type_config in DATA_TYPES.items():
    for urgency in DATA_URGENCY_LEVELS:
        for qos in DATA_QOS_LEVELS:
            # 根据数据类型和紧急度选择合适的安全级别
            if data_type == "TASK_CMD":
                security_levels = ["secret", "confidential"]
            elif data_type == "INTEL":
                security_levels = ["top_secret", "secret"]
            elif data_type == "DATA_SLICE":
                security_levels = ["confidential", "public"]
            else:  # RAW_IMAGE
                security_levels = ["public"]
            
            for security in security_levels:
                # 计算组合的优先级调整因子
                urgency_factor = {
                    "immediate": 1.5,
                    "urgent": 1.2,
                    "normal": 1.0,
                    "low": 0.8
                }[urgency]
                
                qos_factor = {
                    "high": 1.3,
                    "medium": 1.0,
                    "low": 0.7
                }[qos]
                
                # 计算调整后的等待时限
                adjusted_delay = int(type_config.get("max_wait_limit", MAX_WAIT_LIMIT) / urgency_factor)
                
                # 计算调整后的基础价值
                adjusted_value = type_config["base_value"] * urgency_factor * qos_factor
                
                # 创建组合ID
                combo_id = f"{data_type}_{urgency}_{qos}_{security}"
                
                DATA_COMBINATIONS.append({
                    "id": combo_id,
                    "base_type": data_type,
                    "type_name": type_config["name"],
                    "urgency": urgency,
                    "qos": qos,
                    "security": security,
                    "size_range": type_config["size_range"],
                    "size_unit": type_config["size_unit"],
                    "priority_range": type_config["priority_range"],
                    "max_delay": adjusted_delay,
                    "allowed_links": type_config["allowed_links"],
                    "beta": type_config["beta"],
                    "base_value": adjusted_value,
                    "immediate": type_config.get("immediate", False)
                })

# 记录组合数量
TOTAL_DATA_COMBINATIONS = len(DATA_COMBINATIONS)
logger.debug("Generated %d data type combinations", TOTAL_DATA_COMBINATIONS)

# 仿真时间加速因子
# 说明：TIME_SCALE决定仿真速度，值越大卫星移动越快
# - TIME_SCALE = 1: 实时（1真实秒 = 1仿真秒），非常慢
# - TIME_SCALE = 10: 轨道平滑，易观察（推荐演示）
# - TIME_SCALE = 60: 快速仿真，卫星看起来跳跃
# - TIME_SCALE = 600: 极速仿真，用于长时间测试
TIME_SCALE = 10  # 仿真速度，保持平滑动画

# 地面站配置
DEFAULT_GROUND_STATION_COUNT = 20  # 默认选择20个地面站
MIN_GROUND_STATION_COUNT = 5       # 最少5个
MAX_GROUND_STATION_COUNT = 50      # 最多50个(全部)

# ⭐ LEO卫星配置
DEFAULT_LEO_SATELLITE_COUNT = 8    # 默认选择8颗LEO卫星
MIN_LEO_SATELLITE_COUNT = 1        # 最少1颗
# 移除MAX_LEO_SATELLITE_COUNT上限


# ==========================================
# 4. 数据任务类
# ==========================================
class ContentTask:
    """内容任务 - 带时效性衰减的数据价值模型"""

    def __init__(self, task_type):
        self.type = task_type
        if task_type in DATA_TYPES:
            cfg = DATA_TYPES[task_type]
            self.beta = cfg['beta']
            self.base_value = cfg['base_value']
        else:
            params = {
                'SAR': (0.15, 100.0),
                'OPTICAL': (0.05, 80.0),
                'IOT': (0.001, 40.0),
                'CONTROL': (0.5, 150.0),
                'INFRARED': (0.03, 70.0),
                'COMM': (0.02, 60.0)
            }
            self.beta, self.base_value = params.get(task_type, (0.02, 60.0))
        self.creation_time = 0

    def get_dynamic_value(self, current_time):
        """计算当前时刻的数据价值"""
        dt = current_time - self.creation_time
        return self.base_value * math.exp(-self.beta * dt)


# ==========================================
# 4.5 数据传输请求类
# ==========================================
class TransmissionRequest:
    """数据传输请求 - 与卫星绑定"""
    _id_counter = 0
    _id_lock = threading.Lock()  # 保护跨线程的 ID 自增

    def __init__(self, data_type, data_size, priority, max_delay,
                 start_time=None, end_time=None, satellite_id=None, source="user",
                 experiment_requirements=None, selected_ground_stations=None):
        # 线程安全地分配唯一请求编号，避免并发提交产生重复 REQ_ 编号
        with TransmissionRequest._id_lock:
            TransmissionRequest._id_counter += 1
            self.id = f"REQ_{TransmissionRequest._id_counter:04d}"
        self.data_type = data_type
        self.data_size = data_size
        self.priority = priority
        self.max_delay = max_delay  # 等待时限（秒）
        self.start_time = start_time
        self.end_time = end_time
        self.satellite_id = satellite_id
        self.source = source  # "user" 或 "background"
        self.selected_ground_stations = selected_ground_stations or []  # ⭐ 用户选定的地面站列表
        
        # 实验要求字段
        self.experiment_requirements = experiment_requirements or {}
        self.test_mode = self.experiment_requirements.get("test_mode", False)
        self.error_injection = self.experiment_requirements.get("error_injection", None)
        self.telemetry_level = self.experiment_requirements.get("telemetry_level", "normal")
        self.custom_constraints = self.experiment_requirements.get("custom_constraints", {})
        
        self.status = "pending"
        self.reject_reason = None
        self.assigned_link = None
        self.submit_time = None
        self.start_transmit_time = None
        self.complete_time = None
        self.progress = 0.0
        self.transmission_rate = 0.0
        self.selected_ground_station = None
        self.selected_relay = None
        self.selected_relay2 = None  # 第二跳中继(用于星间链路)
        self.transmission_method = None
        self.predicted_pass_time = None  # 预测的过境时间
        
        # ⭐ 新增时延统计字段
        self.wait_time = 0.0           # 等待时延（从提交到开始传输）
        self.transmission_time = 0.0   # 传输时延（从开始传输到完成）
        
    def to_dict(self):
        # 计算当前等待时间（如果还在等待）
        current_wait = self.wait_time
        if self.status == "accepted" and self.submit_time:
            current_wait = 0  # 将在前端实时计算
            
        return {
            "id": self.id,
            "data_type": self.data_type,
            "data_type_name": DATA_TYPES.get(self.data_type, {}).get("name", self.data_type),
            "data_size": self.data_size,
            "priority": self.priority,
            "max_delay": self.max_delay,  # 等待时限
            "start_time": self.start_time,
            "end_time": self.end_time,
            "satellite_id": self.satellite_id,
            "source": self.source,
            "status": self.status,
            "reject_reason": self.reject_reason,
            "assigned_link": self.assigned_link,
            "submit_time": self.submit_time,
            "start_transmit_time": self.start_transmit_time,
            "complete_time": self.complete_time,
            "progress": self.progress,
            "transmission_rate": self.transmission_rate,
            "selected_ground_station": self.selected_ground_station,
            "selected_relay": self.selected_relay,
            "selected_relay2": self.selected_relay2,
            "transmission_method": self.transmission_method,
            "predicted_pass_time": self.predicted_pass_time,
            "wait_time": self.wait_time,               # ⭐ 等待时延
            "transmission_time": self.transmission_time, # ⭐ 传输时延
            "experiment_requirements": self.experiment_requirements,
            "test_mode": self.test_mode,
            "error_injection": self.error_injection,
            "telemetry_level": self.telemetry_level,
            "custom_constraints": self.custom_constraints
        }


# ==========================================
# 5. 仿真引擎
# ==========================================
class SimulationEngine:
    """仿真引擎核心 - 管理卫星、地面站、传输任务"""
    
    def __init__(self, ground_station_count=DEFAULT_GROUND_STATION_COUNT, leo_satellite_count=DEFAULT_LEO_SATELLITE_COUNT):
        self.current_time = 0.0
        self.running = False
        # ⭐ 使用 RLock（可重入锁）减少死锁风险
        self.lock = threading.RLock()

        # ⭐ LEO卫星列表 (从预定义轨道中选择指定数量)
        self.all_leo_satellites = LEO_SATELLITES  # 所有可用的LEO卫星(轨道预先已知)
        self.leo_satellite_count = max(MIN_LEO_SATELLITE_COUNT, leo_satellite_count)
        self.leo_satellites = self.all_leo_satellites[:self.leo_satellite_count]  # 选择前N颗

        self.meo_satellites = MEO_SATELLITES
        self.geo_relays = GEO_RELAY_SATELLITES

        # 地面站列表 (从50个中随机选择指定数量)
        self.all_ground_stations = CHINA_GROUND_STATIONS
        self.ground_station_count = max(MIN_GROUND_STATION_COUNT, 
                                        min(ground_station_count, MAX_GROUND_STATION_COUNT))
        self.ground_stations = random.sample(self.all_ground_stations, self.ground_station_count)

        # 传输请求队列
        self.transmission_requests = []
        self.request_history = []

        # 资源占用跟踪（简单版）
        self.resource_usage = {
            "satellites": {},    # {sat_id: [req_ids]}
            "ground_stations": {},  # {gs_id: [req_ids]}
            "geo_relays": {}     # {geo_id: [req_ids]}
        }
        
        # ⭐ 新增：时间维度资源池（记录每个资源在各时间段的占用情况）
        # 结构: {resource_id: [(start_time, end_time, req_id, bandwidth), ...]}
        self.resource_time_pool = {
            "satellites": {},      # 卫星时间占用
            "ground_stations": {}, # 地面站时间占用
            "geo_relays": {}       # 中继星时间占用
        }
        
        # 初始化资源池
        for sat in self.leo_satellites:
            self.resource_time_pool["satellites"][sat.sat_id] = []
        for gs in self.all_ground_stations:
            self.resource_time_pool["ground_stations"][gs["id"]] = []
        for geo in self.geo_relays:
            self.resource_time_pool["geo_relays"][geo["id"]] = []
        
        # 背景任务生成器配置（降低频率以提高性能）
        self.background_task_enabled = False  # ⭐ 关闭背景任务，便于调试
        self.background_task_interval = 30.0  # 每30秒生成一个背景任务（原10秒）
        self.last_background_task_time = 0.0
        
        # 统计数据
        self.stats = {
            "total_requests": 0,
            "user_requests": 0,           # 用户提交的请求
            "background_requests": 0,      # 背景自动任务
            "accepted_requests": 0,
            "rejected_requests": 0,
            "rejected_by_resource": 0,     # 因资源不足拒绝
            "transmitting_requests": 0,
            "completed_requests": 0,
            "total_data_transmitted": 0.0,
            "resource_utilization": {      # 资源利用率
                "satellites": 0.0,
                "ground_stations": 0.0,
                "geo_relays": 0.0
            },
            # ⭐ 新增决策指标统计
            "decision_metrics": {
                "acceptance_rate": 0.0,        # 接受率 = accepted / total
                "completion_rate": 0.0,        # 完成率 = completed / accepted
                "avg_scheduling_time": 0.0,    # 平均调度时间(秒)
                "avg_transmission_time": 0.0,  # 平均传输时间(秒)
                "throughput_mbps": 0.0,        # 吞吐量 (Mbps)
                "total_scheduling_time": 0.0,  # 累计调度时间
                "total_transmission_time": 0.0,# 累计传输时间
                "scheduling_count": 0,         # 调度次数
                "transmission_count": 0        # 传输完成次数
            },
            # ⭐ 拒绝原因分布统计
            "rejection_distribution": {}
        }
        
        # 开始仿真
        self.start_simulation()

    def reset_requests(self):
        """Clear all request/runtime transmission state for a fresh server start."""
        with self.lock:
            self.transmission_requests.clear()
            self.request_history.clear()
            TransmissionRequest._id_counter = 0
            self.resource_usage = {
                "satellites": {},
                "ground_stations": {},
                "geo_relays": {}
            }
            self.resource_time_pool = {
                "satellites": {sat.sat_id: [] for sat in self.leo_satellites},
                "ground_stations": {gs["id"]: [] for gs in self.all_ground_stations},
                "geo_relays": {geo["id"]: [] for geo in self.geo_relays}
            }
            self.stats.update({
                "total_requests": 0,
                "user_requests": 0,
                "background_requests": 0,
                "accepted_requests": 0,
                "rejected_requests": 0,
                "rejected_by_resource": 0,
                "transmitting_requests": 0,
                "completed_requests": 0,
                "total_data_transmitted": 0.0,
                "resource_utilization": {
                    "satellites": 0.0,
                    "ground_stations": 0.0,
                    "geo_relays": 0.0
                },
                "decision_metrics": {
                    "acceptance_rate": 0.0,
                    "completion_rate": 0.0,
                    "avg_scheduling_time": 0.0,
                    "avg_transmission_time": 0.0,
                    "throughput_mbps": 0.0,
                    "total_scheduling_time": 0.0,
                    "total_transmission_time": 0.0,
                    "scheduling_count": 0,
                    "transmission_count": 0
                },
                "rejection_distribution": {},
                "relay_bandwidth_usage": {}
            })

    def _log(self, message, level="normal", request=None):
        """
        统一日志输出方法 - 支持遥测级别控制
        
        Args:
            message: 日志消息
            level: 日志级别 ("high", "normal", "low")
            request: 关联的请求对象（可选）
        """
        # 如果有关联请求，使用请求的遥测级别
        if request:
            telemetry_level = request.telemetry_level
        else:
            telemetry_level = "normal"
        
        # 日志级别映射：high > normal > low
        level_priority = {"high": 3, "normal": 2, "low": 1}
        telemetry_priority = {"high": 3, "normal": 2, "low": 1}
        
        # 只输出优先级 <= 遥测级别的日志
        if level_priority.get(level, 2) <= telemetry_priority.get(telemetry_level, 2):
            # 添加时间戳和级别标记
            timestamp = time.strftime("%H:%M:%S", time.localtime())
            level_tag = {
                "high": "[HIGH]",
                "normal": "[INFO]",
                "low": "[DEBUG]"
            }.get(level, "[INFO]")
            
            req_tag = f"[REQ:{request.id}]" if request else ""
            print(f"{timestamp} {level_tag}{req_tag} {message}")
    
    def start_simulation(self):
        """启动仿真线程"""
        self.running = True
        self.simulation_thread = threading.Thread(target=self._simulation_loop, daemon=True)
        self.simulation_thread.start()
    
    def _simulation_loop(self):
        """仿真主循环"""
        last_time = time.time()
        error_count = 0
        max_consecutive_errors = 10
        
        while self.running:
            try:
                current_real_time = time.time()
                delta_real = current_real_time - last_time
                last_time = current_real_time
                
                # 仿真时间推进
                delta_sim = delta_real * TIME_SCALE
                
                with self.lock:
                    self.current_time += delta_sim
                    
                    # 生成背景任务
                    if self.background_task_enabled:
                        self._generate_background_tasks()
                    
                    # 更新资源利用率统计
                    self._update_resource_utilization()
                    
                    # ⭐ 更新决策指标
                    self._update_decision_metrics()
                    
                    # 更新传输任务
                    self._update_transmissions(delta_sim)
                
                # 成功执行，重置错误计数
                error_count = 0
                time.sleep(0.01)  # ⭐ 10ms更新间隔，提高动画流畅度
                
            except Exception as e:
                error_count += 1
                import traceback
                tb = traceback.format_exc()
                print(f"[ERROR] 仿真循环异常 ({error_count}/{max_consecutive_errors}): {e}")
                print(tb)
                # ⭐ 可观测：保留最近的循环异常（供调试接口查询），不静默吞掉
                recent = getattr(self, "_loop_errors", [])
                recent.append({"time": time.time(), "error": str(e), "traceback": tb})
                self._loop_errors = recent[-20:]

                if error_count >= max_consecutive_errors:
                    print(f"[FATAL] 连续错误超过{max_consecutive_errors}次，仿真循环终止")
                    break
                
                time.sleep(0.1)  # 出错后短暂等待
    
    def _generate_background_tasks(self):
        """自动生成背景回传任务"""
        if self.current_time - self.last_background_task_time >= self.background_task_interval:
            self.last_background_task_time = self.current_time
            
            # 随机选择数据类型(背景任务倾向于小数据)
            data_types = ["TASK_CMD", "INTEL", "DATA_SLICE"]
            weights = [0.5, 0.3, 0.2]
            data_type = random.choices(data_types, weights=weights)[0]
            
            # 根据类型生成数据大小（DATA_TYPES 只有 size_range/size_unit，无 typical_size）
            data_config = DATA_TYPES.get(data_type, {})
            size_range = data_config.get("size_range", (1, 100))
            if not isinstance(size_range, (tuple, list)) or len(size_range) < 2:
                size_range = (1, 100)
            # data_size 单位与该数据类型的 size_unit 一致（与用户请求口径相同）
            data_size = random.uniform(size_range[0], size_range[1])
            
            # 背景任务优先级较低
            priority = random.randint(1, 2)
            max_delay = random.uniform(1800, 3600)
            
            # 选择负载最低的卫星
            satellite_loads = {}
            for sat in self.leo_satellites:
                load = sum(1 for r in self.transmission_requests 
                          if r.satellite_id == sat.sat_id 
                          and r.data_type == data_type
                          and r.status in ["accepted", "transmitting"])
                satellite_loads[sat.sat_id] = load
            
            min_load = min(satellite_loads.values())
            candidates = [sat for sat in self.leo_satellites if satellite_loads[sat.sat_id] == min_load]
            satellite = random.choice(candidates)
            
            # 创建背景任务
            req = TransmissionRequest(
                data_type=data_type,
                data_size=data_size,
                priority=priority,
                max_delay=max_delay,
                satellite_id=satellite.sat_id,
                source="background"
            )
            req.submit_time = self.current_time
            
            self.stats["total_requests"] += 1
            self.stats["background_requests"] += 1
            
            # 评估并尝试启动
            accepted, reason = self._evaluate_request(req, satellite)
            
            if accepted:
                req.status = "accepted"
                self.transmission_requests.append(req)
                self.stats["accepted_requests"] += 1
                self._start_transmission(req, satellite)
            else:
                req.status = "rejected"
                req.reject_reason = reason
                self.request_history.append(req)
                self.stats["rejected_requests"] += 1
    
    def _update_resource_utilization(self):
        """更新资源利用率统计 - 基于带宽的精确算法"""
        
        # ⭐ 新算法：
        # 1. 卫星: 只要有请求分配(包括等待)就算占用
        # 2. 地面站: 只统计正在传输(transmitting)的请求
        # 3. 中继: 基于带宽占用率计算，一个中继可以同时服务多个任务
        
        # 计算卫星利用率 - 包括等待和传输中的请求
        total_satellites = len(self.leo_satellites)
        occupied_satellites = sum(1 for sat_id, req_list in self.resource_usage["satellites"].items() if len(req_list) > 0)
        self.stats["resource_utilization"]["satellites"] = (occupied_satellites / total_satellites) if total_satellites > 0 else 0.0
        
        # 计算地面站利用率 - 仅统计正在传输的请求
        total_ground_stations = len(self.ground_stations)
        transmitting_ground_stations = set()
        for req in self.transmission_requests:
            if req.status == "transmitting" and req.selected_ground_station:
                transmitting_ground_stations.add(req.selected_ground_station)
        self.stats["resource_utilization"]["ground_stations"] = (len(transmitting_ground_stations) / total_ground_stations) if total_ground_stations > 0 else 0.0
        
        # ⭐ 计算GEO中继带宽利用率 - 基于实际带宽占用
        # 每个中继有固定带宽（2000 Mbps），统计所有正在传输的任务占用的带宽
        relay_bandwidth_usage = {}  # {relay_id: used_bandwidth}
        
        for req in self.transmission_requests:
            if req.status == "transmitting":
                # 检查第一跳中继
                if req.selected_relay:
                    if req.selected_relay not in relay_bandwidth_usage:
                        relay_bandwidth_usage[req.selected_relay] = 0
                    relay_bandwidth_usage[req.selected_relay] += req.transmission_rate
                
                # 检查第二跳中继
                if req.selected_relay2:
                    if req.selected_relay2 not in relay_bandwidth_usage:
                        relay_bandwidth_usage[req.selected_relay2] = 0
                    relay_bandwidth_usage[req.selected_relay2] += req.transmission_rate
        
        # 计算平均带宽利用率
        total_geo_relays = len(self.geo_relays)
        if total_geo_relays > 0:
            total_bandwidth_utilization = 0
            for geo in self.geo_relays:
                relay_bandwidth = geo.get("bandwidth", 1600)  # 默认1600 Mbps
                used_bandwidth = relay_bandwidth_usage.get(geo["id"], 0)
                utilization = min(1.0, used_bandwidth / relay_bandwidth) if relay_bandwidth > 0 else 0
                total_bandwidth_utilization += utilization
            
            self.stats["resource_utilization"]["geo_relays"] = total_bandwidth_utilization / total_geo_relays
        else:
            self.stats["resource_utilization"]["geo_relays"] = 0.0
        
        # ⭐ 保存详细的中继带宽使用情况，供前端显示
        self.stats["relay_bandwidth_usage"] = relay_bandwidth_usage
    
    def _update_decision_metrics(self):
        """⭐ 更新决策指标统计"""
        metrics = self.stats["decision_metrics"]
        
        # 接受率
        total = self.stats["total_requests"]
        if total > 0:
            metrics["acceptance_rate"] = self.stats["accepted_requests"] / total
        
        # 完成率
        accepted = self.stats["accepted_requests"]
        if accepted > 0:
            metrics["completion_rate"] = self.stats["completed_requests"] / accepted
        
        # 平均调度时间
        if metrics["scheduling_count"] > 0:
            metrics["avg_scheduling_time"] = metrics["total_scheduling_time"] / metrics["scheduling_count"]
        
        # 平均传输时间
        if metrics["transmission_count"] > 0:
            metrics["avg_transmission_time"] = metrics["total_transmission_time"] / metrics["transmission_count"]
        
        # 吞吐量 (当前传输速率总和)
        total_rate = sum(req.transmission_rate for req in self.transmission_requests 
                        if req.status == "transmitting")
        metrics["throughput_mbps"] = total_rate
    
    def _record_rejection(self, reason_code):
        """⭐ 记录拒绝原因分布"""
        if reason_code not in self.stats["rejection_distribution"]:
            self.stats["rejection_distribution"][reason_code] = 0
        self.stats["rejection_distribution"][reason_code] += 1
    
    # ==========================================
    # ⭐ 资源池时间管理函数
    # ==========================================
    
    def _check_time_slot_available(self, resource_type, resource_id, start_time, end_time, required_bandwidth=0):
        """
        检查指定资源在指定时间段内是否可用
        
        Args:
            resource_type: "satellites", "ground_stations", "geo_relays"
            resource_id: 资源ID
            start_time: 开始时间（仿真时间）
            end_time: 结束时间（仿真时间）
            required_bandwidth: 需要的带宽（仅对中继有效）
        
        Returns:
            (bool, str): (是否可用, 原因)
        """
        if resource_type not in self.resource_time_pool:
            return False, "无效的资源类型"
        
        if resource_id not in self.resource_time_pool[resource_type]:
            return False, f"资源 {resource_id} 不存在"
        
        time_slots = self.resource_time_pool[resource_type][resource_id]
        
        # 检查时间段冲突
        for slot in time_slots:
            slot_start, slot_end, req_id, slot_bw = slot
            
            # 检查是否有时间重叠
            if not (end_time <= slot_start or start_time >= slot_end):
                # 对于中继，检查带宽是否超限
                if resource_type == "geo_relays":
                    geo = next((g for g in self.geo_relays if g["id"] == resource_id), None)
                    if geo:
                        max_bw = geo.get("bandwidth", 2000)
                        # 计算该时间段内已占用带宽
                        used_bw = sum(s[3] for s in time_slots 
                                     if not (end_time <= s[0] or start_time >= s[1]))
                        if used_bw + required_bandwidth > max_bw:
                            return False, f"中继 {resource_id} 带宽不足 (已用:{used_bw:.0f}, 需要:{required_bandwidth:.0f}, 上限:{max_bw})"
                else:
                    # 卫星和地面站：时间段冲突即不可用
                    return False, f"资源 {resource_id} 在时间段 {slot_start:.0f}-{slot_end:.0f} 已被 {req_id} 占用"
        
        return True, "可用"
    
    def _reserve_time_slot(self, resource_type, resource_id, start_time, end_time, req_id, bandwidth=0):
        """
        预约资源时间段
        
        Args:
            resource_type: 资源类型
            resource_id: 资源ID
            start_time: 开始时间
            end_time: 结束时间
            req_id: 请求ID
            bandwidth: 占用带宽
        """
        if resource_type in self.resource_time_pool and resource_id in self.resource_time_pool[resource_type]:
            self.resource_time_pool[resource_type][resource_id].append(
                (start_time, end_time, req_id, bandwidth)
            )
    
    def _release_time_slot(self, req_id):
        """
        释放指定请求占用的所有时间段
        
        Args:
            req_id: 请求ID
        """
        for resource_type in self.resource_time_pool:
            for resource_id in self.resource_time_pool[resource_type]:
                self.resource_time_pool[resource_type][resource_id] = [
                    slot for slot in self.resource_time_pool[resource_type][resource_id]
                    if slot[2] != req_id
                ]
    
    def _cleanup_expired_time_slots(self):
        """清理已过期的时间段占用"""
        current_time = self.current_time
        for resource_type in self.resource_time_pool:
            for resource_id in self.resource_time_pool[resource_type]:
                self.resource_time_pool[resource_type][resource_id] = [
                    slot for slot in self.resource_time_pool[resource_type][resource_id]
                    if slot[1] > current_time  # 保留结束时间大于当前时间的
                ]
    
    def _get_resource_schedule(self, resource_type, resource_id, time_range=3600):
        """
        获取资源的时间占用计划
        
        Args:
            resource_type: 资源类型
            resource_id: 资源ID  
            time_range: 查看的时间范围（秒）
        
        Returns:
            list: 时间占用列表
        """
        if resource_type not in self.resource_time_pool:
            return []
        if resource_id not in self.resource_time_pool[resource_type]:
            return []
        
        current_time = self.current_time
        end_time = current_time + time_range
        
        return [
            {
                "start": slot[0],
                "end": slot[1],
                "request_id": slot[2],
                "bandwidth": slot[3]
            }
            for slot in self.resource_time_pool[resource_type][resource_id]
            if slot[1] > current_time and slot[0] < end_time
        ]
    
    def _estimate_transmission_time(self, data_size_mb, rate_mbps):
        """估算传输时间（秒）"""
        if rate_mbps <= 0:
            return float('inf')
        return (data_size_mb * 8) / rate_mbps  # 数据量(MB) * 8 / 速率(Mbps) = 时间(秒)

    def _data_size_to_mb(self, req):
        """将请求 data_size 按其数据类型的 size_unit 统一归一到 MB。

        所有换算点（进度计算、时间窗校验、吞吐累计）统一复用本函数，避免 KB/MB/GB 混算。
        """
        data_config = DATA_TYPES.get(req.data_type, {})
        size_unit = data_config.get("size_unit", "MB")
        size = req.data_size or 0
        if size_unit == "KB":
            return size / 1024
        if size_unit == "GB":
            return size * 1024
        return size

    def _update_transmissions(self, delta_time):
        """更新所有传输任务的进度 (包含动态链路切换逻辑)"""
        for req in self.transmission_requests[:]:
            # ==================================================
            # 1. 处理等待中的请求 (尝试开始传输)
            # ==================================================
            if req.status == "accepted":
                # 检查等待中的请求是否已满足传输条件
                # 找到对应的卫星
                satellite = None
                for sat in self.leo_satellites:
                    if sat.sat_id == req.satellite_id:
                        satellite = sat
                        break
                
                if satellite:
                    sat_pos = self.get_satellite_position(satellite)
                    
                    # 检查是否有可用链路(带资源独占检查)
                    best_rate = 0
                    best_method = None
                    best_gs = None
                    best_relay = None
                    best_relay2 = None
                    
                    # ⭐ 判断是否为立即传输类型
                    is_immediate_type = req.data_type in ["TASK_CMD", "INTEL"]
                    
                    # 资源可用性检查内部函数
                    def is_resource_available(sat_id, gs_id, relay_id=None, relay2_id=None):
                        # ⭐ TASK_CMD/INTEL 完全跳过资源独占检查
                        if is_immediate_type:
                            # 只检查中继带宽
                            if relay_id and not self._check_relay_bandwidth_available(relay_id, 10): return False
                            if relay2_id and not self._check_relay_bandwidth_available(relay2_id, 10): return False
                            return True  # 不检查卫星和地面站独占
                        
                        # 非立即传输类型
                        if sat_id in self.resource_usage["satellites"] and len(self.resource_usage["satellites"][sat_id]) > 0:
                            # 如果是自己占用的，则允许（比如原始影像等待过境）
                            if req.id not in self.resource_usage["satellites"][sat_id]:
                                return False
                        if gs_id in self.resource_usage["ground_stations"] and len(self.resource_usage["ground_stations"][gs_id]) > 0:
                            return False
                        # 中继带宽检查逻辑
                        if relay_id and not self._check_relay_bandwidth_available(relay_id, 10): return False
                        if relay2_id and not self._check_relay_bandwidth_available(relay2_id, 10): return False
                        return True
                    
                    # --- 链路搜索逻辑 (同 _start_transmission) ---
                    # 1. 尝试直连
                    for gs in self.ground_stations:
                        if self.check_visibility(sat_pos, gs):
                            if is_resource_available(satellite.sat_id, gs["id"]):
                                rate = self._calculate_direct_rate(sat_pos, gs, req.data_type)
                                if rate > best_rate:
                                    best_rate = rate
                                    best_method = "direct"
                                    best_gs = gs["id"]
                                    best_relay = None; best_relay2 = None
                    
                    # 2. 尝试中继 (若允许)
                    data_config = DATA_TYPES.get(req.data_type, {})
                    if "relay" in data_config.get("allowed_links", []):
                        for geo in self.geo_relays:
                            geo_pos = self.get_geo_position(geo)
                            if self.check_geo_visibility(sat_pos, geo_pos):
                                for gs in self.ground_stations:
                                    if self.check_visibility(geo_pos, gs, min_elevation=5):
                                        if is_resource_available(satellite.sat_id, gs["id"], geo["id"]):
                                            rate = self._calculate_relay_rate(sat_pos, geo_pos, gs, req.data_type)
                                            if rate > best_rate:
                                                best_rate = rate
                                                best_method = "relay"
                                                best_gs = gs["id"]
                                                best_relay = geo["id"]
                                                best_relay2 = None
                        
                        # 3. 尝试双跳 (LEO -> GEO1 -> GEO2 -> GS)
                        if best_rate == 0:
                            for geo1 in self.geo_relays:
                                geo1_pos = self.get_geo_position(geo1)
                                if not self.check_geo_visibility(sat_pos, geo1_pos):
                                    continue
                                for geo2 in self.geo_relays:
                                    if geo2["id"] == geo1["id"]:
                                        continue
                                    geo2_pos = self.get_geo_position(geo2)
                                    for gs in self.ground_stations:
                                        if not self.check_visibility(geo2_pos, gs, min_elevation=5):
                                            continue
                                        rate = self._calculate_multi_hop_relay_rate(
                                            sat_pos, geo1_pos, geo2_pos, gs, req.data_type
                                        )
                                        if rate > best_rate and is_resource_available(
                                            satellite.sat_id, gs["id"], geo1["id"], geo2["id"]
                                        ):
                                            best_rate = rate
                                            best_method = "relay"
                                            best_gs = gs["id"]
                                            best_relay = geo1["id"]
                                            best_relay2 = geo2["id"]

                    # 如果找到链路,开始传输
                    if best_rate > 0:
                        req.status = "transmitting"
                        req.start_transmit_time = self.current_time
                        req.transmission_rate = best_rate
                        req.transmission_method = best_method
                        req.selected_ground_station = best_gs
                        req.selected_relay = best_relay
                        req.selected_relay2 = best_relay2
                        self.stats["transmitting_requests"] += 1
                        
                        # 占用资源
                        self._occupy_resources(req.id, satellite.sat_id, best_gs, best_relay, best_relay2)
                        
                        # ⭐ 记录调度时间
                        scheduling_time = self.current_time - req.submit_time
                        self.stats["decision_metrics"]["total_scheduling_time"] += scheduling_time
                        self.stats["decision_metrics"]["scheduling_count"] += 1
                        
                        self._log(f"等待结束开始传输 - 方式:{best_method}, 速率:{best_rate:.1f}Mbps", request=req)
                    else:
                        # 检查等待超时
                        wait_time = self.current_time - req.submit_time
                        max_wait = req.max_delay if hasattr(req, 'max_delay') else MAX_WAIT_LIMIT
                        if wait_time > max_wait:
                            req.status = "rejected"
                            req.reject_reason = REJECTION_REASONS["TIMEOUT_WAIT"]
                            req.wait_time = wait_time  # 记录实际等待时间
                            self._record_rejection("TIMEOUT_WAIT")
                            self.transmission_requests.remove(req)
                            self.request_history.append(req)
                            self.stats["accepted_requests"] -= 1
                            self.stats["rejected_requests"] += 1
                            # 释放可能锁定的卫星资源
                            self._release_resources(req.id)

            # ==================================================
            # 2. 处理传输中的请求 (进度更新 + 动态切换)
            # ==================================================
            elif req.status == "transmitting":
                # 获取卫星对象用于位置计算
                satellite = next((s for s in self.leo_satellites if s.sat_id == req.satellite_id), None)
                
                if satellite:
                    sat_pos = self.get_satellite_position(satellite)

                    if not self._current_link_available(req, sat_pos):
                        if not self._reroute_transmission(req, satellite, sat_pos):
                            self._log("当前传输链路不可见且无可用替代链路，传输中断", request=req, level="normal")
                            self._interrupt_request(req, "LINK_INTERRUPTED")
                            continue

                    # --------------------------------------------------
                    # ⭐⭐⭐ 核心修改：动态链路切换逻辑 (中继 -> 地面站) ⭐⭐⭐
                    # --------------------------------------------------
                    # 条件：当前用的是中继，且数据类型允许直连
                    if req.transmission_method in ["relay", "multi_relay"]:
                        data_config = DATA_TYPES.get(req.data_type, {})
                        if "direct" in data_config.get("allowed_links", []):
                            
                            # 遍历寻找是否有更好的地面站机会
                            for gs in self.ground_stations:
                                # 检查可见性 (设定 min_elevation=15 防止频繁切换不稳定的低仰角链路)
                                if self.check_visibility(sat_pos, gs, min_elevation=15):
                                    
                                    # 检查该地面站是否空闲 (或已被自己占用)
                                    gs_free = gs["id"] not in self.resource_usage["ground_stations"]
                                    
                                    if gs_free:
                                        # 计算潜在的新速率
                                        new_rate = self._calculate_direct_rate(sat_pos, gs, req.data_type)
                                        
                                        # 切换阈值：新速率必须比当前快 20% 才切换，避免乒乓效应
                                        if new_rate > req.transmission_rate * HANDOVER_RATE_RATIO:
                                            self._log(f"🔄 触发链路切换: 中继 -> 地面站 ({gs['name']}) 速率提升: {req.transmission_rate:.0f}->{new_rate:.0f}", request=req, level="high")
                                            
                                            # 1. 释放旧的中继资源 (手动操作资源字典)
                                            if req.selected_relay and req.selected_relay in self.resource_usage["geo_relays"]:
                                                if req.id in self.resource_usage["geo_relays"][req.selected_relay]:
                                                    self.resource_usage["geo_relays"][req.selected_relay].remove(req.id)
                                            
                                            if req.selected_relay2 and req.selected_relay2 in self.resource_usage["geo_relays"]:
                                                if req.id in self.resource_usage["geo_relays"][req.selected_relay2]:
                                                    self.resource_usage["geo_relays"][req.selected_relay2].remove(req.id)
                                                    
                                            # 注意：不要释放卫星资源，因为还在同一颗卫星上
                                            # 注意：不要释放地面站资源，因为之前是中继到地面，如果之前的地面站和现在不同，需要释放旧的
                                            if req.selected_ground_station and req.selected_ground_station != gs["id"]:
                                                if req.selected_ground_station in self.resource_usage["ground_stations"]:
                                                    if req.id in self.resource_usage["ground_stations"][req.selected_ground_station]:
                                                        self.resource_usage["ground_stations"][req.selected_ground_station].remove(req.id)

                                            # 2. 占用新的地面站资源
                                            if gs["id"] not in self.resource_usage["ground_stations"]:
                                                self.resource_usage["ground_stations"][gs["id"]] = []
                                            self.resource_usage["ground_stations"][gs["id"]].append(req.id)
                                            
                                            # 3. 更新请求状态
                                            req.transmission_method = "direct"
                                            req.selected_ground_station = gs["id"]
                                            req.selected_relay = None
                                            req.selected_relay2 = None
                                            req.transmission_rate = new_rate
                                            
                                            # 找到一个就切换，跳出循环
                                            break
                    # --------------------------------------------------
                    # 结束动态切换逻辑
                    # --------------------------------------------------

                # 更新传输进度
                if req.transmission_rate > 0:
                    # ⭐ 修复: 正确计算传输数据量
                    # transmission_rate 单位是 Mbps (Megabits per second)
                    # delta_time 单位是秒
                    # 数据量 = 速率(Mbps) × 时间(s) / 8 = MegaBytes
                    data_transmitted_mb = req.transmission_rate * delta_time / 8  # MB
                    
                    # ⭐ 根据数据类型统一转换 data_size 到 MB
                    data_size_mb = self._data_size_to_mb(req)

                    # 错误注入：中断
                    if req.error_injection and req.error_injection.get("type") == "interrupt":
                         if random.random() < 0.01: # 1%概率中断
                             self._interrupt_request(req, "LINK_INTERRUPTED")
                             continue

                    # ⭐ 使用正确的单位计算进度
                    if data_size_mb > 0:
                        req.progress = min(100.0, req.progress + (data_transmitted_mb / data_size_mb) * 100)
                    
                    if req.progress >= 100.0:
                        req.status = "completed"
                        req.complete_time = self.current_time
                        
                        # ⭐ 记录传输时间
                        if req.start_transmit_time:
                            transmission_time = self.current_time - req.start_transmit_time
                            self.stats["decision_metrics"]["total_transmission_time"] += transmission_time
                            self.stats["decision_metrics"]["transmission_count"] += 1
                        
                        self.transmission_requests.remove(req)
                        self.request_history.append(req)
                        self.stats["transmitting_requests"] -= 1
                        self.stats["completed_requests"] += 1
                        
                        # 释放资源
                        self._release_resources(req.id)
                        # 累加归一后的 MB，避免 KB/MB/GB 混加导致吞吐量失真
                        self.stats["total_data_transmitted"] += data_size_mb
                        
                        self._log(
                            f"传输完成 - 耗时:{self.current_time - req.start_transmit_time:.1f}s, "
                            f"最终方式:{req.transmission_method}",
                            level="normal",
                            request=req
                        )
    def get_satellite_position(self, satellite, current_time=None):
        """获取卫星位置"""
        if current_time is None:
            current_time = self.current_time
        lat, lon, alt = satellite.propagate(current_time)
        return {"lat": lat, "lon": lon, "alt": alt}
    
    def get_geo_position(self, geo_relay):
        """获取GEO卫星固定位置"""
        return {"lat": 0, "lon": geo_relay["lon"], "alt": 35786000}
    
    def check_visibility(self, sat_pos, gs_pos, min_elevation=10):
        """检查卫星与地面站的可见性"""
        # 计算中心角
        angle = calc_central_angle(sat_pos["lat"], sat_pos["lon"], gs_pos["lat"], gs_pos["lon"])
        
        # 地球半径(公里)
        R = 6371.0
        h = sat_pos["alt"] / 1000.0  # 转换为公里
        
        # 计算地面距离(公里)
        d = R * math.radians(angle)
        
        # 计算仰角
        if d < 0.001:  # 接近正上方
            elevation = 90.0
        else:
            # 使用余弦定理计算卫星到地面站的直线距离
            slant_range = math.sqrt(R*R + (R+h)*(R+h) - 2*R*(R+h)*math.cos(math.radians(angle)))
            # 计算仰角
            elevation = math.degrees(math.asin((R+h)*math.sin(math.radians(angle))/slant_range)) - angle
        
        return elevation >= min_elevation
    
    def check_geo_visibility(self, leo_pos, geo_pos):
        """检查LEO卫星与GEO中继星的可见性"""
        angle = calc_central_angle(leo_pos["lat"], leo_pos["lon"], geo_pos["lat"], geo_pos["lon"])
        visible = angle < 80
        # ⭐ 调试日志 - 可注释掉
        # if visible:
        #     print(f"   GEO @ {geo_pos['lon']}° 可见 LEO @ ({leo_pos['lat']:.1f}°, {leo_pos['lon']:.1f}°), 角度: {angle:.1f}°")
        return visible
    
    def _resource_busy_by_other(self, resource_type, resource_id, req_id):
        return any(
            existing_req_id != req_id
            for existing_req_id in self.resource_usage.get(resource_type, {}).get(resource_id, [])
        )

    def _ground_station_candidates(self, req):
        if req.selected_ground_stations:
            selected = set(req.selected_ground_stations)
            return [gs for gs in self.ground_stations if gs["id"] in selected]
        return self.ground_stations

    def _relay_can_carry_request(self, relay_id, required_rate, req):
        if relay_id in [req.selected_relay, req.selected_relay2]:
            return True
        return self._check_relay_bandwidth_available(relay_id, required_rate)

    def _find_best_available_link(self, req, satellite, sat_pos):
        data_config = DATA_TYPES.get(req.data_type, {})
        allowed_links = data_config.get("allowed_links", ["direct"])
        is_immediate_type = req.data_type in ["TASK_CMD", "INTEL"]
        best_link = None
        best_rate = 0

        def can_use_satellite():
            return is_immediate_type or not self._resource_busy_by_other("satellites", satellite.sat_id, req.id)

        def can_use_ground_station(gs_id):
            return is_immediate_type or not self._resource_busy_by_other("ground_stations", gs_id, req.id)

        if "direct" in allowed_links and can_use_satellite():
            for gs in self._ground_station_candidates(req):
                if can_use_ground_station(gs["id"]) and self.check_visibility(sat_pos, gs, min_elevation=10):
                    rate = self._calculate_direct_rate(sat_pos, gs, req.data_type)
                    if rate > best_rate:
                        best_rate = rate
                        best_link = {
                            "method": "direct",
                            "ground_station": gs["id"],
                            "relay": None,
                            "relay2": None,
                            "rate": rate
                        }

        if "relay" in allowed_links and can_use_satellite():
            for geo in self.geo_relays:
                geo_pos = self.get_geo_position(geo)
                if not self.check_geo_visibility(sat_pos, geo_pos):
                    continue
                for gs in self._ground_station_candidates(req):
                    if not can_use_ground_station(gs["id"]):
                        continue
                    if not self.check_visibility(geo_pos, gs, min_elevation=5):
                        continue
                    rate = self._calculate_relay_rate(sat_pos, geo_pos, gs, req.data_type)
                    if rate > best_rate and self._relay_can_carry_request(geo["id"], rate, req):
                        best_rate = rate
                        best_link = {
                            "method": "relay",
                            "ground_station": gs["id"],
                            "relay": geo["id"],
                            "relay2": None,
                            "rate": rate
                        }

        return best_link

    def _current_link_available(self, req, sat_pos):
        if req.transmission_method == "direct":
            gs = next((item for item in self.ground_stations if item["id"] == req.selected_ground_station), None)
            return bool(gs and self.check_visibility(sat_pos, gs, min_elevation=5))

        if req.transmission_method == "relay":
            geo = next((item for item in self.geo_relays if item["id"] == req.selected_relay), None)
            gs = next((item for item in self.ground_stations if item["id"] == req.selected_ground_station), None)
            if not geo or not gs:
                return False
            geo_pos = self.get_geo_position(geo)
            return self.check_geo_visibility(sat_pos, geo_pos) and self.check_visibility(geo_pos, gs, min_elevation=5)

        if req.transmission_method == "multi_relay":
            geo1 = next((item for item in self.geo_relays if item["id"] == req.selected_relay), None)
            geo2 = next((item for item in self.geo_relays if item["id"] == req.selected_relay2), None)
            gs = next((item for item in self.ground_stations if item["id"] == req.selected_ground_station), None)
            if not geo1 or not geo2 or not gs:
                return False
            geo1_pos = self.get_geo_position(geo1)
            geo2_pos = self.get_geo_position(geo2)
            geo_gap = calc_central_angle(geo1_pos["lat"], geo1_pos["lon"], geo2_pos["lat"], geo2_pos["lon"])
            return (
                self.check_geo_visibility(sat_pos, geo1_pos)
                and geo_gap < 140
                and self.check_visibility(geo2_pos, gs, min_elevation=5)
            )

        return False

    def _apply_link_assignment(self, req, satellite, link):
        self._release_resources(req.id)
        req.transmission_method = link["method"]
        req.selected_ground_station = link["ground_station"]
        req.selected_relay = link["relay"]
        req.selected_relay2 = link["relay2"]
        req.transmission_rate = link["rate"]
        self._occupy_resources(
            req.id,
            satellite.sat_id,
            req.selected_ground_station,
            req.selected_relay,
            req.selected_relay2
        )

    def _reroute_transmission(self, req, satellite, sat_pos):
        link = self._find_best_available_link(req, satellite, sat_pos)
        if not link:
            return False
        old_method = req.transmission_method
        self._apply_link_assignment(req, satellite, link)
        self._log(
            f"链路重调度: {old_method} -> {req.transmission_method}, 速率:{req.transmission_rate:.1f}Mbps",
            request=req,
            level="normal"
        )
        return True

    def _interrupt_request(self, req, reason_code="LINK_INTERRUPTED"):
        req.status = "rejected"
        req.reject_reason = REJECTION_REASONS[reason_code]
        self._record_rejection(reason_code)
        if req in self.transmission_requests:
            self.transmission_requests.remove(req)
        self.request_history.append(req)
        self.stats["transmitting_requests"] = max(0, self.stats.get("transmitting_requests", 0) - 1)
        self.stats["rejected_requests"] += 1
        self._release_resources(req.id)

    def submit_request(self, request_data):
        """提交用户传输请求 - 基于实时资源占用决策"""
        with self.lock:
            # 智能选择LEO卫星 - 避免同类型请求集中在一颗卫星
            # 统计各卫星当前负载(相同数据类型的请求数)
            data_type = request_data.get("data_type")
            # ⭐ 支持指定卫星ID
            satellite_id = request_data.get("satellite_id")
            if satellite_id:
                # 查找指定的卫星
                satellite = None
                for sat in self.leo_satellites:
                    if sat.sat_id == satellite_id:
                        satellite = sat
                        break
                if not satellite:
                    # 标准化拒绝结果（结构与正常返回对齐），并补充日志与统计计数
                    reason = f"未找到指定的卫星: {satellite_id}"
                    self.stats["total_requests"] += 1
                    self.stats["user_requests"] += 1
                    self.stats["rejected_requests"] += 1
                    self._record_rejection("SATELLITE_NOT_FOUND")
                    self._log(f"请求被拒绝 - {reason}", level="normal")
                    return {
                        "status": "error",
                        "reject_reason": reason,
                        "error": reason,
                        "available_satellites": [s.sat_id for s in self.leo_satellites],
                    }
            else:
                # 如果没有指定卫星，使用负载均衡选择
                satellite_loads = {}
                for sat in self.leo_satellites:
                    # 统计该卫星上相同类型的活跃请求
                    load = sum(1 for r in self.transmission_requests 
                              if r.satellite_id == sat.sat_id 
                              and r.data_type == data_type
                              and r.status in ["accepted", "transmitting"])
                    satellite_loads[sat.sat_id] = load
                
                # 选择负载最低的卫星(如果有多个则随机选一个)
                min_load = min(satellite_loads.values())
                candidates = [sat for sat in self.leo_satellites if satellite_loads[sat.sat_id] == min_load]
                satellite = random.choice(candidates)
            
            # ⭐ 处理选中的地面站列表（保存到请求对象，供后续调度使用）
            selected_ground_stations = request_data.get("selected_ground_stations", [])
            
            # ⭐ 处理时间段参数
            start_time = request_data.get("start_time")
            end_time = request_data.get("end_time")
            
            # 如果前端传递的是偏移量，则计算实际时间
            start_time_offset = request_data.get("start_time_offset")
            time_window_duration = request_data.get("time_window_duration")
            
            if start_time_offset is not None and time_window_duration is not None:
                # 基于当前仿真时间计算实际时间段
                start_time = self.current_time + start_time_offset
                end_time = start_time + time_window_duration
            
            # 提取实验要求字段
            experiment_requirements = request_data.get("experiment_requirements", {})
            
            req = TransmissionRequest(
                data_type=data_type,
                data_size=request_data.get("data_size"),
                priority=request_data.get("priority"),
                max_delay=request_data.get("max_delay"),
                start_time=start_time,
                end_time=end_time,
                satellite_id=satellite.sat_id,
                source="user",  # 标记为用户请求
                experiment_requirements=experiment_requirements,
                selected_ground_stations=selected_ground_stations  # ⭐ 传递选定的地面站列表
            )
            req.submit_time = self.current_time
            
            self.stats["total_requests"] += 1
            self.stats["user_requests"] += 1
            
            # 评估请求 - 重点检查资源可用性
            accepted, reason = self._evaluate_request(req, satellite)
            
            if accepted:
                req.status = "accepted"
                self.transmission_requests.append(req)
                self.stats["accepted_requests"] += 1
                
                # ⭐ 遥测日志：请求接受
                time_info = ""
                if req.start_time is not None:
                    time_info = f", 时间段:{req.start_time:.0f}-{req.end_time:.0f}"
                self._log(
                    f"请求已接受 - 类型:{req.data_type}, 优先级:{req.priority}, "
                    f"卫星:{satellite.sat_id}{time_info}",
                    level="normal",
                    request=req
                )
                
                # 立即开始传输（带异常保护）
                try:
                    self._start_transmission(req, satellite)
                except Exception as e:
                    import traceback
                    print(f"⚠️ _start_transmission 异常: {str(e)}\n{traceback.format_exc()}")
                    # 不崩溃，让请求保持 accepted 状态等待后续处理
            else:
                req.status = "rejected"
                req.reject_reason = reason
                self.request_history.append(req)
                self.stats["rejected_requests"] += 1
                
                # ⭐ 遥测日志：请求拒绝
                self._log(
                    f"请求被拒绝 - 原因:{reason}",
                    level="normal",
                    request=req
                )
                
                # 统计因资源不足拒绝的情况
                if "资源" in reason or "占用" in reason or "时间" in reason:
                    self.stats["rejected_by_resource"] += 1
            
            return req.to_dict()
    
    def _validate_time_window(self, req, estimated_rate):
        """⭐ 新增：校验时间窗口是否满足传输需求"""
        if req.start_time is not None and req.end_time is not None:
            available_duration = req.end_time - req.start_time  # 可用时间(秒)
            if available_duration <= 0:
                return False, "TIME_WINDOW_INVALID"
            
            # 计算所需传输时间 (data_size单位可能是KB/MB/GB) - 统一归一到 MB
            data_size_mb = self._data_size_to_mb(req)

            # 计算所需时间 (秒) = 数据量(MB) / 速率(Mbps) * 8
            if estimated_rate > 0:
                required_duration = (data_size_mb * 8) / estimated_rate
                if required_duration > available_duration:
                    return False, "TIME_WINDOW_INVALID"
        
        return True, None
    
    def _check_time_window_resources(self, req, satellite):
        """
        ⭐ 检查用户指定时间段内的资源可用性
        
        Args:
            req: 请求对象（包含start_time, end_time）
            satellite: 分配的卫星
        
        Returns:
            (bool, str): (是否可用, 原因)
        """
        start_time = req.start_time
        end_time = req.end_time
        
        # 1. 检查时间段有效性
        if start_time >= end_time:
            return False, REJECTION_REASONS["TIME_WINDOW_INVALID"]
        
        # 计算数据大小（统一归一到 MB）
        data_size_mb = self._data_size_to_mb(req)

        # 估算传输速率（根据数据类型）
        estimated_rate = 100  # 默认100 Mbps
        if req.data_type == "RAW_IMAGE":
            estimated_rate = 150  # 直连速率较高
        elif req.data_type in ["TASK_CMD", "INTEL"]:
            estimated_rate = 200  # 小数据速率更高
        
        # 计算所需传输时间
        required_duration = self._estimate_transmission_time(data_size_mb, estimated_rate)
        available_duration = end_time - start_time
        
        if required_duration > available_duration:
            return False, f"时间窗口不足: 需要{required_duration:.0f}秒, 可用{available_duration:.0f}秒"
        
        # 2. 检查卫星资源可用性
        sat_available, sat_reason = self._check_time_slot_available(
            "satellites", satellite.sat_id, start_time, end_time
        )
        if not sat_available:
            return False, f"卫星资源冲突: {sat_reason}"
        
        # 3. 检查传输路径资源
        # 原始影像只能直连，检查地面站
        if req.data_type == "RAW_IMAGE":
            # 需要找到一个可用的地面站
            gs_found = False
            for gs in self.ground_stations:
                gs_id = gs["id"]
                gs_available, _ = self._check_time_slot_available(
                    "ground_stations", gs_id, start_time, end_time
                )
                if gs_available:
                    gs_found = True
                    break
            
            if not gs_found:
                return False, "指定时间段内无可用地面站"
        else:
            # 其他类型：优先地面站，其次中继
            gs_found = False
            for gs in self.ground_stations:
                gs_id = gs["id"]
                gs_available, _ = self._check_time_slot_available(
                    "ground_stations", gs_id, start_time, end_time
                )
                if gs_available:
                    gs_found = True
                    break
            
            if not gs_found:
                # 尝试中继
                relay_found = False
                for geo in self.geo_relays:
                    geo_id = geo["id"]
                    geo_available, _ = self._check_time_slot_available(
                        "geo_relays", geo_id, start_time, end_time, estimated_rate
                    )
                    if geo_available:
                        relay_found = True
                        break
                
                if not relay_found:
                    return False, "指定时间段内无可用地面站或中继资源"
        
        return True, "时间段资源可用"

    def _evaluate_request(self, req, satellite):
        """评估请求是否可以被接受 - 基于实时资源利用率和时间段决策"""
        
        # ⭐ 实验要求：测试模式下，放宽资源检查
        if req.test_mode:
            # 测试模式：直接接受，用于快速验证功能
            return True, "测试模式：直接接受"
        
        # 特殊处理：指令类型（TASK_CMD）立即接受，无需等待过境
        data_config = DATA_TYPES.get(req.data_type, {})
        if data_config.get("immediate", False):
            # 指令类型直接接受，稍后会自动寻找传输机会
            return True, "指令类型立即接受"
        
        # ⭐ 新增：检查用户指定的时间段
        if req.start_time is not None and req.end_time is not None:
            # 用户指定了具体时间段，需要检查资源池可用性
            time_check_result = self._check_time_window_resources(req, satellite)
            if not time_check_result[0]:
                self._record_rejection("TIME_WINDOW_CONFLICT")
                return False, time_check_result[1]
        
        # 第0步：检查资源利用率阈值
        # 如果系统资源紧张，对低优先级请求（特别是背景任务）更严格
        resource_util = self.stats["resource_utilization"]
        avg_utilization = (resource_util["satellites"] + resource_util["ground_stations"] + resource_util["geo_relays"]) / 3
        
        # ⭐ 实验要求：自定义约束 - 强制中继
        force_relay = req.custom_constraints.get("force_relay", False)
        
        # 资源紧张阈值判断
        RESOURCE_TIGHT_THRESHOLD = CFG_RESOURCE_TIGHT_THRESHOLD  # 资源紧张阈值（见 config）
        if avg_utilization > RESOURCE_TIGHT_THRESHOLD:
            # 背景任务在资源紧张时更容易被拒绝
            if req.source == "background" and req.priority < 5:  # 只拒绝低优先级背景任务
                return False, f"系统资源紧张(利用率{avg_utilization*100:.1f}%),背景任务暂停"
            # 用户低优先级请求也可能被拒绝（但阈值更低）
            elif req.source == "user" and req.priority < 2:  # 只拒绝优先级<2的用户请求
                return False, f"系统资源紧张(利用率{avg_utilization*100:.1f}%),低优先级请求拒绝"
        
        # 第1步：检查卫星资源是否已被占用
        if satellite.sat_id in self.resource_usage["satellites"] and len(self.resource_usage["satellites"][satellite.sat_id]) > 0:
            return False, f"卫星{satellite.sat_id}资源已被占用"
        
        sat_pos = self.get_satellite_position(satellite)
        
        # ⭐ 实验要求：自定义约束 - 指定地面站
        preferred_gs = req.custom_constraints.get("preferred_ground_station", None)
        
        # 策略1: 尝试直连链路(当前可见性)
        # ⭐ 如果强制中继，跳过直连检查
        if not force_relay and "direct" in data_config.get("allowed_links", ["direct"]):
            for gs in self.ground_stations:
                # 检查地面站是否已被占用
                gs_id = gs["id"]  # 地面站恒为 dict
                if gs_id in self.resource_usage["ground_stations"] and len(self.resource_usage["ground_stations"][gs_id]) > 0:
                    continue
                
                # ⭐ 实验要求：如果指定了首选地面站，只检查该站
                if preferred_gs and gs_id != preferred_gs:
                    continue
                
                if self.check_visibility(sat_pos, gs):
                    return True, None
        
        # 策略2: 尝试中继链路(当前可见性)
        if "relay" in data_config.get("allowed_links", []):
            # ⭐ 实验要求：自定义约束 - 指定中继星
            preferred_relay = req.custom_constraints.get("preferred_relay", None)
            
            for geo in self.geo_relays:
                # 检查GEO是否已被占用
                geo_id = geo["id"]  # 中继恒为 dict
                if geo_id in self.resource_usage["geo_relays"] and len(self.resource_usage["geo_relays"][geo_id]) > 0:
                    continue
                
                # ⭐ 实验要求：如果指定了首选中继星，只检查该星
                if preferred_relay and geo_id != preferred_relay:
                    continue
                    
                geo_pos = self.get_geo_position(geo)
                
                # 检查LEO到GEO可见性
                if not self.check_geo_visibility(sat_pos, geo_pos):
                    continue
                
                # 检查GEO到地面站可见性
                for gs in self.ground_stations:
                    # 检查地面站是否已被占用
                    gs_id = gs["id"]  # 地面站恒为 dict
                    if gs_id in self.resource_usage["ground_stations"] and len(self.resource_usage["ground_stations"][gs_id]) > 0:
                        continue
                    
                    # ⭐ 实验要求：如果指定了首选地面站，只检查该站
                    if preferred_gs and gs_id != preferred_gs:
                        continue
                    
                    if self.check_visibility(geo_pos, gs, min_elevation=5):
                        return True, None

        # 策略3: 对于原始影像(RAW_IMAGE)等数据,预测未来过境机会
        # 基于卫星轨道特征,在max_delay时间内预测是否会有过境机会
        if req.data_type == "RAW_IMAGE" or "direct" in data_config.get("allowed_links", []):
            # 预测未来一段时间内的过境机会(简化:检查未来几个轨道周期)
            orbital_period = satellite.get_orbital_period()  # 秒
            max_prediction_time = min(req.max_delay, orbital_period * 2)  # 最多预测2个轨道周期
            
            # 粗略预测:每隔轨道周期的1/10检查一次
            time_step = orbital_period / 10
            for future_offset in range(1, int(max_prediction_time / time_step) + 1):
                future_time = self.current_time + future_offset * time_step
                future_sat_pos = self.get_satellite_position(satellite, future_time)
                
                # 检查未来时刻是否过境任一地面站
                for gs in self.ground_stations:
                    if self.check_visibility(future_sat_pos, gs):
                        # 找到过境机会,接受请求但标记为等待状态
                        req.predicted_pass_time = future_time
                        return True, None
        
        return False, "无可用通信链路或资源不足"
    
    def _start_transmission(self, req, satellite):
        """开始传输任务(或等待过境) - 支持中继带宽共享"""
        sat_pos = self.get_satellite_position(satellite)
        
        # 选择传输路径
        best_rate = 0
        best_method = None
        best_gs = None
        best_relay = None
        best_relay2 = None  # 第二跳中继
        
        # 获取数据类型配置（提前获取，供内部函数使用）
        data_config = DATA_TYPES.get(req.data_type, {})
        is_raw_image = (req.data_type == "RAW_IMAGE")
        is_task_cmd = (req.data_type == "TASK_CMD")
        is_intel_info = (req.data_type == "INTEL")
        is_immediate_type = is_task_cmd or is_intel_info  # ⭐ 立即传输类型
        
        # ⭐ 获取可用的地面站列表（优先使用用户选定的，否则使用所有地面站）
        def get_available_ground_stations():
            """获取可用的地面站列表"""
            if req.selected_ground_stations and len(req.selected_ground_stations) > 0:
                # 使用用户选定的地面站列表
                return [gs for gs in self.ground_stations if gs["id"] in req.selected_ground_stations]
            else:
                # 使用所有地面站
                return self.ground_stations
        
        available_ground_stations = get_available_ground_stations()
        
        # ⭐ 改进的资源可用性检查 - 中继支持带宽共享
        def is_resource_available(sat_id, gs_id, relay_id=None, relay2_id=None, required_rate=0):
            """检查资源是否可用"""
            # ⭐ TASK_CMD/INTEL 完全跳过资源独占检查，它们数据量小可共享
            if is_immediate_type:
                # 只检查中继带宽是否足够
                if relay_id:
                    if not self._check_relay_bandwidth_available(relay_id, required_rate):
                        return False
                if relay2_id:
                    if not self._check_relay_bandwidth_available(relay2_id, required_rate):
                        return False
                return True  # ⭐ 不检查卫星和地面站独占
            
            # 非立即传输类型：检查卫星独占
            if sat_id in self.resource_usage["satellites"] and len(self.resource_usage["satellites"][sat_id]) > 0:
                return False
            # 检查地面站 - 独占
            if gs_id and gs_id in self.resource_usage["ground_stations"] and len(self.resource_usage["ground_stations"][gs_id]) > 0:
                return False
            # ⭐ 检查中继星 - 基于带宽共享
            if relay_id:
                if not self._check_relay_bandwidth_available(relay_id, required_rate):
                    return False
            if relay2_id:
                if not self._check_relay_bandwidth_available(relay2_id, required_rate):
                    return False
            return True

        # ============================================
        # 根据数据类型选择传输策略
        # ============================================
        
        if is_raw_image:
            # RAW_IMAGE禁止中继，只能直连地面站
            for gs in available_ground_stations:  # ⭐ 使用用户选定的地面站列表
                if self.check_visibility(sat_pos, gs):
                    if is_resource_available(satellite.sat_id, gs["id"]):
                        rate = self._calculate_direct_rate(sat_pos, gs, req.data_type)
                        if rate > best_rate:
                            best_rate = rate
                            best_method = "direct"
                            best_gs = gs["id"]
                            best_relay = None
                            best_relay2 = None
            
            # 如果当前没有地面站可见，检查未来是否有过境机会
            if best_rate == 0:
                has_future_pass = self._check_future_ground_station_pass(satellite, req.max_delay)
                if not has_future_pass:
                    req.status = "rejected"
                    req.reject_reason = REJECTION_REASONS["RAW_IMAGE_NO_DIRECT"]
                    self._record_rejection("RAW_IMAGE_NO_DIRECT")
                    self.transmission_requests.remove(req)
                    self.request_history.append(req)
                    self.stats["accepted_requests"] -= 1
                    self.stats["rejected_requests"] += 1
                    return
                # 有未来过境机会，锁定卫星等待
                self._occupy_satellite_only(req.id, satellite.sat_id)
                
        else:
            # ⭐⭐⭐ 其他所有类型（TASK_CMD/INTEL/DATA_SLICE）：优先直连，无直连则中继 ⭐⭐⭐
            # 第一步：尝试直连地面站
            for gs in available_ground_stations:  # ⭐ 使用用户选定的地面站列表
                if self.check_visibility(sat_pos, gs):
                    if is_resource_available(satellite.sat_id, gs["id"]):
                        rate = self._calculate_direct_rate(sat_pos, gs, req.data_type)
                        if rate > best_rate:
                            best_rate = rate
                            best_method = "direct"
                            best_gs = gs["id"]
                            best_relay = None
                            best_relay2 = None
            
            # 第二步：如果没有直连，尝试中继
            if best_rate == 0:
                for geo in self.geo_relays:
                    geo_pos = self.get_geo_position(geo)
                    # 检查 LEO -> GEO 可见性
                    if self.check_geo_visibility(sat_pos, geo_pos):
                        # 检查 GEO -> 地面站 可见性
                        for gs in available_ground_stations:  # ⭐ 使用用户选定的地面站列表
                            if self.check_visibility(geo_pos, gs, min_elevation=5):
                                rate = self._calculate_relay_rate(sat_pos, geo_pos, gs, req.data_type)
                                # 对于TASK_CMD/INTEL，只检查中继带宽
                                if is_immediate_type:
                                    if rate > 0 and self._check_relay_bandwidth_available(geo["id"], rate):
                                        if rate > best_rate:
                                            best_rate = rate
                                            best_method = "relay"
                                            best_gs = gs["id"]
                                            best_relay = geo["id"]
                                            best_relay2 = None
                                else:
                                    # 其他类型正常检查资源
                                    if is_resource_available(satellite.sat_id, gs["id"], geo["id"], None, rate):
                                        if rate > best_rate:
                                            best_rate = rate
                                            best_method = "relay"
                                            best_gs = gs["id"]
                                            best_relay = geo["id"]
                                            best_relay2 = None

            # 第三步：若单跳中继仍不可达，尝试双跳中继 (LEO -> GEO1 -> GEO2 -> GS)
            if best_rate == 0:
                for geo1 in self.geo_relays:
                    geo1_pos = self.get_geo_position(geo1)
                    if not self.check_geo_visibility(sat_pos, geo1_pos):
                        continue
                    for geo2 in self.geo_relays:
                        if geo2["id"] == geo1["id"]:
                            continue
                        geo2_pos = self.get_geo_position(geo2)
                        for gs in available_ground_stations:
                            if not self.check_visibility(geo2_pos, gs, min_elevation=5):
                                continue
                            rate = self._calculate_multi_hop_relay_rate(
                                sat_pos, geo1_pos, geo2_pos, gs, req.data_type
                            )
                            if rate <= 0 or rate <= best_rate:
                                continue
                            if is_immediate_type:
                                ok = (self._check_relay_bandwidth_available(geo1["id"], rate)
                                      and self._check_relay_bandwidth_available(geo2["id"], rate))
                            else:
                                ok = is_resource_available(
                                    satellite.sat_id, gs["id"], geo1["id"], geo2["id"], rate
                                )
                            if ok:
                                best_rate = rate
                                best_method = "relay"
                                best_gs = gs["id"]
                                best_relay = geo1["id"]
                                best_relay2 = geo2["id"]

            # 记录选择的传输方式
            if best_rate > 0:
                if best_method == "direct":
                    self._log(f"请求 {req.id} ({req.data_type}) 选择直连: GS={best_gs}, 速率={best_rate:.1f}Mbps", level="normal")
                else:
                    self._log(f"请求 {req.id} ({req.data_type}) 选择中继: GEO={best_relay}, 速率={best_rate:.1f}Mbps", level="normal")
            else:
                # 如果是立即传输类型（TASK_CMD/INTEL）且无可用链路，立即拒绝
                if is_immediate_type:
                    self._log(f"请求 {req.id} ({req.data_type}) 立即拒绝: 无可用链路!", level="high")
                    req.status = "rejected"
                    req.reject_reason = REJECTION_REASONS["NO_VISIBLE_RELAY"]
                    self._record_rejection("NO_VISIBLE_RELAY")
                    self.transmission_requests.remove(req)
                    self.request_history.append(req)
                    self.stats["accepted_requests"] -= 1
                    self.stats["rejected_requests"] += 1
                    return
        
        # ============================================
        # 根据链路搜索结果决定状态
        # ============================================
        if best_rate > 0:
            req.status = "transmitting"
            req.start_transmit_time = self.current_time
            req.progress = 0.0
            req.transmission_rate = best_rate
            
            # ⭐ 错误注入：速率降低
            if req.error_injection and req.error_injection.get("type") == "rate_reduction":
                reduction_factor = req.error_injection.get("factor", 0.5)
                req.transmission_rate = best_rate * reduction_factor
                self._log(
                    f"错误注入：速率降低 {(1-reduction_factor)*100:.0f}% "
                    f"({best_rate:.1f} -> {req.transmission_rate:.1f} Mbps)",
                    level="high",
                    request=req
                )
            else:
                req.transmission_rate = best_rate
            
            req.transmission_method = best_method
            req.selected_ground_station = best_gs
            req.selected_relay = best_relay
            req.selected_relay2 = best_relay2
            self.stats["transmitting_requests"] += 1
            
            # ⭐ 错误注入：传输延迟
            if req.error_injection and req.error_injection.get("type") == "delay":
                delay_seconds = req.error_injection.get("value", 5)
                req.start_transmit_time += delay_seconds
                self._log(
                    f"错误注入：传输延迟 {delay_seconds}s",
                    level="high",
                    request=req
                )
            
            # 标记资源为占用状态（TASK_CMD/INTEL不占用资源）
            if not (is_task_cmd or is_intel_info):
                self._occupy_resources(req.id, satellite.sat_id, best_gs, best_relay, best_relay2)
        else:
            # 没有可用链路，保持accepted状态等待
            req.status = "accepted"
            req.transmission_rate = 0
            req.transmission_method = None
            req.selected_ground_station = None
            req.selected_relay = None
            req.selected_relay2 = None
    
    def _check_future_ground_station_pass(self, satellite, max_delay):
        """检查卫星在max_delay时间内是否有地面站过境机会"""
        # 简化版：检查未来轨道周期内是否会过境任何地面站
        orbital_period = satellite.get_orbital_period()
        check_steps = 20  # 检查20个时间点
        time_step = min(orbital_period / check_steps, max_delay / check_steps)
        
        for i in range(1, check_steps + 1):
            future_time = self.current_time + i * time_step
            if future_time - self.current_time > max_delay:
                break
            future_pos = self.get_satellite_position(satellite, future_time)
            for gs in self.ground_stations:
                if self.check_visibility(future_pos, gs):
                    return True
        return False
    
    def _check_relay_bandwidth_available(self, relay_id, required_rate):
        """检查中继卫星带宽是否充足"""
        # 找到中继卫星配置
        relay = None
        for geo in self.geo_relays:
            if geo["id"] == relay_id:
                relay = geo
                break
        
        if not relay:
            return False
        
        relay_bandwidth = relay.get("bandwidth", 2000)  # 默认2000 Mbps
        
        # 计算当前已占用带宽
        used_bandwidth = 0
        for req in self.transmission_requests:
            if req.status == "transmitting":
                if req.selected_relay == relay_id:
                    used_bandwidth += req.transmission_rate
                if req.selected_relay2 == relay_id:
                    used_bandwidth += req.transmission_rate
        
        # 检查是否有足够剩余带宽
        available_bandwidth = relay_bandwidth - used_bandwidth
        return available_bandwidth >= required_rate
    
    def _occupy_resources(self, req_id, sat_id, gs_id, relay_id=None, relay2_id=None, start_time=None, end_time=None):
        """标记资源为占用状态，同时预留时间槽"""
        if sat_id not in self.resource_usage["satellites"]:
            self.resource_usage["satellites"][sat_id] = []
        if req_id not in self.resource_usage["satellites"][sat_id]:
            self.resource_usage["satellites"][sat_id].append(req_id)
        
        if gs_id:
            if gs_id not in self.resource_usage["ground_stations"]:
                self.resource_usage["ground_stations"][gs_id] = []
            if req_id not in self.resource_usage["ground_stations"][gs_id]:
                self.resource_usage["ground_stations"][gs_id].append(req_id)
        
        if relay_id:
            if relay_id not in self.resource_usage["geo_relays"]:
                self.resource_usage["geo_relays"][relay_id] = []
            if req_id not in self.resource_usage["geo_relays"][relay_id]:
                self.resource_usage["geo_relays"][relay_id].append(req_id)
        
        if relay2_id:
            if relay2_id not in self.resource_usage["geo_relays"]:
                self.resource_usage["geo_relays"][relay2_id] = []
            if req_id not in self.resource_usage["geo_relays"][relay2_id]:
                self.resource_usage["geo_relays"][relay2_id].append(req_id)
        
        # ⭐ 新增：预留时间槽
        if start_time is not None and end_time is not None:
            # 预留卫星时间槽
            self._reserve_time_slot("satellites", sat_id, start_time, end_time, req_id)
            # 预留地面站时间槽
            if gs_id:
                self._reserve_time_slot("ground_stations", gs_id, start_time, end_time, req_id)
            # 预留中继时间槽
            if relay_id:
                self._reserve_time_slot("geo_relays", relay_id, start_time, end_time, req_id)
            if relay2_id:
                self._reserve_time_slot("geo_relays", relay2_id, start_time, end_time, req_id)
    
    def _occupy_satellite_only(self, req_id, sat_id):
        """仅标记卫星资源为占用(用于等待过境的原始影像)"""
        if sat_id not in self.resource_usage["satellites"]:
            self.resource_usage["satellites"][sat_id] = []
        self.resource_usage["satellites"][sat_id].append(req_id)
    
    def _release_resources(self, req_id):
        """释放资源占用和时间槽"""
        for resource_dict in self.resource_usage.values():
            for resource_id, req_list in list(resource_dict.items()):
                if req_id in req_list:
                    req_list.remove(req_id)
                # 清理空列表
                if len(req_list) == 0:
                    del resource_dict[resource_id]
        
        # ⭐ 新增：释放时间槽
        self._release_time_slot(req_id)

    
    def _calculate_direct_rate(self, sat_pos, gs, data_type=None):
        """计算直连链路速率 (Mbps)"""
        angle = calc_central_angle(sat_pos["lat"], sat_pos["lon"], gs["lat"], gs["lon"])
        distance = math.sqrt((sat_pos["alt"] / 1000) ** 2 + (6371 * math.sin(math.radians(angle))) ** 2)
        
        if gs["antenna_type"] == "Ka":
            base_rate = 200  # ⭐ 降低基础速率 800->200
        else:
            base_rate = 100  # ⭐ 降低基础速率 300->100
        
        rate = base_rate * math.exp(-distance / 10000)
        
        # ⭐ 原始影像传输速率
        if data_type == "RAW_IMAGE":
            rate = rate * 0.6
        
        return max(rate, 5)  # ⭐ 降低最小速率
    
    def _calculate_relay_rate(self, sat_pos, geo_pos, gs, data_type=None):
        """计算中继链路速率 (Mbps)"""
        # LEO到GEO
        angle1 = calc_central_angle(sat_pos["lat"], sat_pos["lon"], geo_pos["lat"], geo_pos["lon"])
        dist1 = math.sqrt((geo_pos["alt"] - sat_pos["alt"]) ** 2 / 1e12 + (6371 * math.sin(math.radians(angle1))) ** 2)
        rate1 = 500 * math.exp(-dist1 / 50000)  # ⭐ 降低速率 3000->500
        
        # GEO到地面站
        angle2 = calc_central_angle(geo_pos["lat"], geo_pos["lon"], gs["lat"], gs["lon"])
        dist2 = math.sqrt((geo_pos["alt"] / 1000) ** 2 + (6371 * math.sin(math.radians(angle2))) ** 2)
        rate2 = 400 * math.exp(-dist2 / 40000)  # ⭐ 降低速率 2000->400
        
        rate = min(rate1, rate2)
        
        # ⭐ 原始影像传输速率
        if data_type == "RAW_IMAGE":
            rate = rate * 0.6
        
        return max(rate, 5)  # ⭐ 降低最小速率
    
    def _calculate_inter_satellite_rate(self, geo1_pos, geo2_pos):
        """计算GEO星间链路速率 (Mbps)"""
        angle = calc_central_angle(geo1_pos["lat"], geo1_pos["lon"], geo2_pos["lat"], geo2_pos["lon"])
        # GEO之间的距离
        dist = 2 * geo1_pos["alt"] / 1000 * math.sin(math.radians(angle) / 2)
        # 星间链路通常使用激光通信,速率较高
        rate = 2000 * math.exp(-dist / 40000)
        return max(rate, 100)
    
    def _calculate_multi_hop_relay_rate(self, sat_pos, geo1_pos, geo2_pos, gs, data_type=None):
        """计算多跳中继链路速率 (Mbps) - LEO→GEO1→GEO2→地面站"""
        # LEO到GEO1
        angle1 = calc_central_angle(sat_pos["lat"], sat_pos["lon"], geo1_pos["lat"], geo1_pos["lon"])
        dist1 = math.sqrt((geo1_pos["alt"] - sat_pos["alt"]) ** 2 / 1e12 + (6371 * math.sin(math.radians(angle1))) ** 2)
        rate1 = 1500 * math.exp(-dist1 / 30000)
        
        # GEO1到GEO2 (星间链路)
        rate2 = self._calculate_inter_satellite_rate(geo1_pos, geo2_pos)
        
        # GEO2到地面站
        angle3 = calc_central_angle(geo2_pos["lat"], geo2_pos["lon"], gs["lat"], gs["lon"])
        dist3 = math.sqrt((geo2_pos["alt"] / 1000) ** 2 + (6371 * math.sin(math.radians(angle3))) ** 2)
        rate3 = 1000 * math.exp(-dist3 / 20000)
        
        rate = min(rate1, rate2, rate3)
        
        # ⭐ 优化：原始影像多跳中继速率从12%提升到50%
        if data_type == "RAW_IMAGE":
            rate = rate * 0.5  # 多跳稍慢于直连，但仍然可用
        
        return rate
    
    def update_ground_station_count(self, new_count):
        """更新地面站数量"""
        with self.lock:
            # 验证范围
            new_count = max(MIN_GROUND_STATION_COUNT, min(new_count, MAX_GROUND_STATION_COUNT))
            
            if new_count != self.ground_station_count:
                self.ground_station_count = new_count
                # 重新随机选择地面站
                self.ground_stations = random.sample(self.all_ground_stations, self.ground_station_count)
                return True
            return False
    
    def update_leo_satellite_count(self, new_count):
        """⭐ 更新LEO卫星数量 - 轨道参数预先已知，支持动态生成补充，无上限。

        合并自此前两份重复定义：保留动态生成（_generate_random_leo）与减少时的
        _handle_removed_satellites 处理，并按前后激活列表的 ID 差集精确计算被移除卫星。
        """
        with self.lock:
            # 仅验证最小值
            new_count = max(MIN_LEO_SATELLITE_COUNT, int(new_count))

            old_count = len(self.leo_satellites)
            old_ids = [sat.sat_id for sat in self.leo_satellites]
            if new_count == old_count:
                return False

            # 新数量超过库存时动态生成补充
            current_total = len(self.all_leo_satellites)
            if new_count > current_total:
                for i in range(new_count - current_total):
                    self.all_leo_satellites.append(
                        self._generate_random_leo(current_total + i + 1)
                    )

            # 更新激活的卫星列表（轨道参数已知，位置实时计算）
            self.leo_satellite_count = new_count
            self.leo_satellites = self.all_leo_satellites[:self.leo_satellite_count]

            # 减少卫星时，按前后激活 ID 差集精确处理被移除卫星上的请求
            if new_count < old_count:
                active_ids = set(sat.sat_id for sat in self.leo_satellites)
                removed_sat_ids = [sid for sid in old_ids if sid not in active_ids]
                if removed_sat_ids:
                    self._handle_removed_satellites(removed_sat_ids)

            return True
    
    def _handle_removed_satellites(self, removed_sat_ids):
        """处理被移除卫星上的请求 - 重新分配或拒绝"""
        for req in self.transmission_requests[:]:
            if req.satellite_id in removed_sat_ids:
                # 释放资源
                self._release_resources(req.id)
                
                # 尝试重新分配到其他卫星
                if req.status == "accepted":
                    # 等待中的请求，尝试分配到其他卫星
                    available_sats = [sat for sat in self.leo_satellites 
                                     if sat.sat_id not in self.resource_usage.get("satellites", {})]
                    if available_sats:
                        new_sat = random.choice(available_sats)
                        req.satellite_id = new_sat.sat_id
                        self._start_transmission(req, new_sat)
                    else:
                        # 无可用卫星，拒绝请求
                        req.status = "rejected"
                        req.reject_reason = REJECTION_REASONS["SATELLITE_REMOVED"]
                        self._record_rejection("SATELLITE_REMOVED")
                        self.transmission_requests.remove(req)
                        self.request_history.append(req)
                elif req.status == "transmitting":
                    # 传输中的请求，标记为中断
                    req.status = "rejected"
                    req.reject_reason = REJECTION_REASONS["SATELLITE_REMOVED"]
                    self._record_rejection("SATELLITE_REMOVED")
                    self.transmission_requests.remove(req)
                    self.request_history.append(req)
    
    def get_all_requests(self):
        """获取所有用户请求 (不包括背景任务)"""
        with self.lock:
            all_reqs = self.transmission_requests + self.request_history
            # 只返回用户请求，过滤掉背景任务
            user_reqs = [req for req in all_reqs if req.source == "user"]
            return [req.to_dict() for req in user_reqs]
    
    def get_system_data(self):
        """获取系统完整数据 - 优化锁持有时间"""
        # ⭐ 快速获取关键数据的快照，减少锁持有时间
        with self.lock:
            current_time = self.current_time
            # 复制请求列表引用（快照）
            all_reqs = list(self.transmission_requests) + list(self.request_history)
            stats_copy = self.stats.copy()
            leo_sats = list(self.leo_satellites)
            meo_sats = list(self.meo_satellites)
            geo_relays = list(self.geo_relays)
            ground_stations = list(self.ground_stations)
            all_gs = list(self.all_ground_stations)  # 快照，避免锁外迭代被并发改写
        
        # ⭐ 在锁外进行数据序列化（耗时操作）
        requests_data = [req.to_dict() for req in all_reqs]
        
        data = {
            "time": current_time,
            "satellites": [],
            "ground_stations": [],
            "geo_relays": [],
            "all_ground_stations": all_gs,
            "requests": requests_data,
            "stats": stats_copy
        }
        
        # LEO卫星（在锁外计算位置）
        for sat in leo_sats:
            pos = self.get_satellite_position(sat)
            data["satellites"].append({
                "id": sat.sat_id,
                "name": sat.name,
                "type": "LEO",
                "lat": pos["lat"],
                "lon": pos["lon"],
                "alt": pos["alt"],
                "orbit_period": sat.get_orbital_period()
            })
        
        # MEO卫星
        for sat in meo_sats:
            pos = self.get_satellite_position(sat)
            data["satellites"].append({
                "id": sat.sat_id,
                "name": sat.name,
                "type": "MEO",
                "lat": pos["lat"],
                "lon": pos["lon"],
                "alt": pos["alt"],
                "orbit_period": sat.get_orbital_period()
            })
        
        # GEO中继星
        for geo in geo_relays:
            pos = self.get_geo_position(geo)
            data["geo_relays"].append({
                "id": geo["id"],
                "name": geo["name"],
                "lat": pos["lat"],
                "lon": pos["lon"],
                "alt": pos["alt"],
                "antenna": geo["antenna"],
                "beams": geo["beams"],
                "bandwidth": geo["bandwidth"]
            })
        
        # 地面站
        for gs in ground_stations:
            data["ground_stations"].append(gs)
        
        return data
    
    def get_stats(self):
        """获取统计数据（用于资源利用率API）"""
        with self.lock:
            return self.stats.copy()
# ==========================================
# 在 SimulationEngine 类中添加/修改以下方法
# ==========================================

    def _generate_random_leo(self, index):
        """动态生成随机LEO卫星轨道"""
        # 基础参数围绕典型LEO轨道波动
        base_alt = 6871  # 约500km高度
        import random
        
        # 随机分布参数以避免重叠
        altitude = base_alt + random.uniform(-50, 50)
        raan = random.uniform(0, 360)        # 升交点赤经随机
        mean_anomaly = random.uniform(0, 360) # 平近点角随机
        inclination = 97.4 + random.uniform(-1, 1) # 太阳同步轨道附近
        
        return OrbitalElements(
            name=f"扩展卫星_{index}", 
            sat_id=f"LEO_EXT_{index}", 
            semi_major_axis=altitude, 
            eccentricity=0.001, 
            inclination=inclination, 
            raan=raan, 
            arg_perigee=0, 
            mean_anomaly=mean_anomaly
        )

# 全局仿真引擎实例
simulation_engine = SimulationEngine()
