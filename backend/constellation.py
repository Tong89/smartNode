# -*- coding: utf-8 -*-
"""星座与地面站静态配置。

从 core.py 抽离的物理资源清单（50 个境内地面站、LEO/MEO/GEO 星座、随遇接入相控阵站、
LEO 天线配置）。保持原 dict/对象结构不变，仅迁移位置；引擎初始化结果与重构前完全一致。
"""
from backend.orbit import OrbitalElements

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
