# -*- coding: utf-8 -*-
"""激光星间链路（Laser ISL）物理模型。

为 LEO-GEO 与 GEO-GEO 星间链路提供基于激光通信的精确物理模型，包括：

- **地球遮挡判定**：检验两颗卫星之间的视线是否穿越地球（椭球面），判定几何可见性。
- **激光链路预算**：基于激光发射功率、望远镜口径、光束发散角，计算几何损耗与接收功率。
- **指向损耗（捕获跟踪指向, ATP）**：考虑指向误差与平台抖动带来的附加损耗。
- **可达速率**：结合接收光功率、探测器灵敏度与调制格式估算可达数据率。

物理模型参考
------------
- 激光通信自由空间链路方程（参考 Hecht, "The Laser Guidebook"）
- Saleh & Teich, "Fundamentals of Photonics"
- ESA SILEX 星间激光链路系统参数

使用示例
--------
>>> from backend.comms.laser_isl import LaserISLModel, check_los_visibility
>>> model = LaserISLModel()
>>> result = model.compute(sat1_pos, sat2_pos)
>>> result.is_visible    # 视线是否可见
>>> result.rate_mbps     # 可达数据率 (Mbps)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from backend.physics.coordinates import lla_to_ecef

# ─────────────────────── 物理常数 ──────────────────────────
SPEED_OF_LIGHT = 2.998e8          # m/s
PLANCK_CONSTANT = 6.626e-34       # J·s
BOLTZMANN_CONSTANT = 1.381e-23    # J/K

# WGS-84 地球椭球（km）
EARTH_A_KM = 6378.137             # 长半轴 (km)
EARTH_B_KM = 6356.752             # 短半轴 (km)

# ────────────────── 默认激光 ISL 参数 ──────────────────────

# 激光波长（m）：1550 nm 是航天激光通信主流窗口
DEFAULT_WAVELENGTH_M = 1550e-9

# 发射功率（W）：典型星载激光终端 0.5 W
DEFAULT_TX_POWER_W = 0.5

# 发射/接收望远镜口径（m）
DEFAULT_TX_APERTURE_M = 0.10      # 10 cm 口径发射天线
DEFAULT_RX_APERTURE_M = 0.10      # 10 cm 口径接收天线

# 光束全角发散角（rad）：典型值 10 μrad 半角 → 20 μrad 全角
DEFAULT_BEAM_DIVERGENCE_RAD = 20e-6

# 发射光学效率（含调制器、准直透镜等）
DEFAULT_TX_OPTICAL_EFF = 0.70

# 接收光学效率（含滤光片、聚焦透镜等）
DEFAULT_RX_OPTICAL_EFF = 0.75

# 指向损耗：捕获跟踪指向（ATP）系统典型残余误差引起的额外损耗 (dB)
DEFAULT_POINTING_LOSS_DB = 2.0

# 其他杂散损耗：极化、接口损耗等 (dB)
DEFAULT_MISC_LOSS_DB = 0.5

# 接收机灵敏度：典型光子每比特数（OOK 调制，BER=1e-9 时约 40 光子/比特）
# 对应最低接收功率按 Prx_min = n_photons * hf * Rb 计算
DEFAULT_PHOTONS_PER_BIT = 40

# 调制格式：OOK (On-Off Keying) 最大原始速率 (Gbps) —— 硬件上限
DEFAULT_MAX_RATE_GBPS = 10.0      # 10 Gbps 为典型目标

# 最低可用数据率阈值 (Mbps)，低于此值认为链路不可用
MIN_USABLE_RATE_MBPS = 1.0


# ═══════════════════════════════════════════════════════════════
#  数据类
# ═══════════════════════════════════════════════════════════════

@dataclass
class LaserISLResult:
    """激光星间链路计算结果。

    Attributes
    ----------
    is_visible : bool
        视线几何可见性（视线不被地球遮挡）。
    distance_km : float
        两卫星间距离 (km)。
    fspl_db : float
        自由空间路径损耗 (dB)，基于望远镜衍射极限模型。
    geometric_loss_db : float
        几何扩散损耗（光束扩展损耗）(dB)。
    pointing_loss_db : float
        捕获跟踪指向损耗 (dB)。
    total_loss_db : float
        总链路损耗 (dB)。
    tx_power_dbw : float
        发射功率 (dBW)。
    received_power_dbw : float
        估算接收光功率 (dBW)。
    sensitivity_dbw : float
        接收机灵敏度（最低可检测功率）对应 1 Gbps 时 (dBW)。
    link_margin_db : float
        链路余量 (dB) = 接收功率 - 灵敏度；负值表示链路不闭合。
    rate_mbps : float
        可达数据率 (Mbps)。
    """
    is_visible: bool
    distance_km: float
    fspl_db: float
    geometric_loss_db: float
    pointing_loss_db: float
    total_loss_db: float
    tx_power_dbw: float
    received_power_dbw: float
    sensitivity_dbw: float
    link_margin_db: float
    rate_mbps: float

    def to_dict(self) -> dict:
        return {
            "is_visible": self.is_visible,
            "distance_km": round(self.distance_km, 3),
            "fspl_db": round(self.fspl_db, 2),
            "geometric_loss_db": round(self.geometric_loss_db, 2),
            "pointing_loss_db": round(self.pointing_loss_db, 2),
            "total_loss_db": round(self.total_loss_db, 2),
            "tx_power_dbw": round(self.tx_power_dbw, 2),
            "received_power_dbw": round(self.received_power_dbw, 2),
            "sensitivity_dbw": round(self.sensitivity_dbw, 2),
            "link_margin_db": round(self.link_margin_db, 2),
            "rate_mbps": round(self.rate_mbps, 3),
        }


@dataclass
class LaserISLModel:
    """激光星间链路物理模型配置。

    参数
    ----
    wavelength_m : float
        激光波长 (m)，默认 1550 nm。
    tx_power_w : float
        发射光功率 (W)，默认 0.5 W。
    tx_aperture_m : float
        发射端望远镜口径 (m)，默认 0.10 m。
    rx_aperture_m : float
        接收端望远镜口径 (m)，默认 0.10 m。
    beam_divergence_rad : float
        光束全角发散角 (rad)，默认 20 μrad。
        若为 None，则按衍射极限 θ ≈ 2.44·λ/D 自动计算。
    tx_optical_eff : float
        发射光学效率（0–1），默认 0.70。
    rx_optical_eff : float
        接收光学效率（0–1），默认 0.75。
    pointing_loss_db : float
        捕获跟踪指向损耗 (dB)，默认 2.0 dB。
    misc_loss_db : float
        其他杂散损耗 (dB)，默认 0.5 dB。
    photons_per_bit : int
        接收机每比特所需最小光子数，默认 40。
    max_rate_gbps : float
        硬件最大原始速率上限 (Gbps)，默认 10 Gbps。
    """
    wavelength_m: float = DEFAULT_WAVELENGTH_M
    tx_power_w: float = DEFAULT_TX_POWER_W
    tx_aperture_m: float = DEFAULT_TX_APERTURE_M
    rx_aperture_m: float = DEFAULT_RX_APERTURE_M
    beam_divergence_rad: Optional[float] = DEFAULT_BEAM_DIVERGENCE_RAD
    tx_optical_eff: float = DEFAULT_TX_OPTICAL_EFF
    rx_optical_eff: float = DEFAULT_RX_OPTICAL_EFF
    pointing_loss_db: float = DEFAULT_POINTING_LOSS_DB
    misc_loss_db: float = DEFAULT_MISC_LOSS_DB
    photons_per_bit: int = DEFAULT_PHOTONS_PER_BIT
    max_rate_gbps: float = DEFAULT_MAX_RATE_GBPS

    def __post_init__(self) -> None:
        if self.beam_divergence_rad is None or self.beam_divergence_rad <= 0:
            # 衍射极限近似：θ_div ≈ 2.44·λ/D（全角）
            self.beam_divergence_rad = 2.44 * self.wavelength_m / self.tx_aperture_m

    def compute(
        self,
        sat1_pos: Dict[str, float],
        sat2_pos: Dict[str, float],
    ) -> LaserISLResult:
        """计算两颗卫星间的激光 ISL 链路。

        Parameters
        ----------
        sat1_pos : dict
            卫星1位置，含 ``lat``（度）、``lon``（度）、``alt``（米）。
        sat2_pos : dict
            卫星2位置，含 ``lat``（度）、``lon``（度）、``alt``（米）。

        Returns
        -------
        LaserISLResult
            激光 ISL 链路预算结果。若 is_visible=False，则 rate_mbps=0。
        """
        # 1. 几何可见性：视线是否被地球遮挡
        visible = check_los_visibility(sat1_pos, sat2_pos)

        # 2. 两星间距离
        dist_km = _distance_km(sat1_pos, sat2_pos)
        dist_m = dist_km * 1e3

        if not visible:
            return LaserISLResult(
                is_visible=False,
                distance_km=dist_km,
                fspl_db=0.0,
                geometric_loss_db=0.0,
                pointing_loss_db=self.pointing_loss_db,
                total_loss_db=float("inf"),
                tx_power_dbw=10.0 * math.log10(max(self.tx_power_w, 1e-30)),
                received_power_dbw=float("-inf"),
                sensitivity_dbw=0.0,
                link_margin_db=float("-inf"),
                rate_mbps=0.0,
            )

        # 3. 激光链路预算
        # 保护极小距离（同位置卫星）
        if dist_m < 1.0:
            dist_m = 1.0

        # 3a. 发射功率 (dBW)
        tx_power_dbw = 10.0 * math.log10(max(self.tx_power_w, 1e-30))

        # 3b. 发射光学增益/效率 (dB)
        tx_eff_db = 10.0 * math.log10(max(self.tx_optical_eff, 1e-10))

        # 3c. 几何扩散损耗：激光在距离 d 处的光斑面积 A_beam = π·(d·θ/2)²
        #     接收孔径面积 A_rx = π·(D_rx/2)²
        #     几何损耗 = A_rx / A_beam = (D_rx / (d·θ))²
        beam_radius_at_rx_m = dist_m * (self.beam_divergence_rad / 2.0)
        beam_area_m2 = math.pi * beam_radius_at_rx_m ** 2
        rx_area_m2 = math.pi * (self.rx_aperture_m / 2.0) ** 2
        # 避免除零
        geometric_loss = max(rx_area_m2 / max(beam_area_m2, 1e-30), 1e-40)
        geometric_loss_db = 10.0 * math.log10(geometric_loss)  # 负值为损耗

        # 3d. 自由空间路径损耗（激光通信等效，与 beam divergence 模型一致）
        #     FSPLopt = (4π·d / λ)² —— 但实际激光链路用几何模型，这里仅作参考
        fspl_db = 20.0 * math.log10(4.0 * math.pi * dist_m / self.wavelength_m)

        # 3e. 接收光学效率 (dB)
        rx_eff_db = 10.0 * math.log10(max(self.rx_optical_eff, 1e-10))

        # 3f. 指向损耗 (dB，已含 ATP 残余误差)
        pointing_loss_db = self.pointing_loss_db

        # 3g. 杂散损耗 (dB)
        misc_loss_db = self.misc_loss_db

        # 3h. 接收光功率 (dBW)
        #   P_rx(dBW) = P_tx + η_tx + L_geometric + η_rx - L_pointing - L_misc
        received_power_dbw = (
            tx_power_dbw
            + tx_eff_db
            + geometric_loss_db   # 负值，即损耗
            + rx_eff_db
            - pointing_loss_db
            - misc_loss_db
        )

        # 4. 接收机灵敏度（光子计数极限，OOK 调制）
        #    P_min = n_photons × h × f × Rb
        #    以 1 Gbps 参考速率计算对应灵敏度
        freq_hz = SPEED_OF_LIGHT / self.wavelength_m
        ref_rate_bps = 1e9  # 1 Gbps 参考速率
        p_min_w = self.photons_per_bit * PLANCK_CONSTANT * freq_hz * ref_rate_bps
        sensitivity_dbw = 10.0 * math.log10(max(p_min_w, 1e-30))

        # 5. 链路余量 (dB)
        link_margin_db = received_power_dbw - sensitivity_dbw

        # 6. 可达数据率
        #    链路余量每 3 dB 对应速率翻倍（简化关系，基于光子计数受限系统）
        #    Rb_achievable = Rb_ref × 10^(margin_db / (10·log10(2)))
        #                  = 1 Gbps × 2^(margin_db / 3)  (以 3 dB 换算)
        if link_margin_db > 0:
            rate_gbps = ref_rate_bps / 1e9 * math.pow(2.0, link_margin_db / 3.0)
        else:
            # 余量不足时按比例折减
            rate_gbps = ref_rate_bps / 1e9 * math.pow(2.0, link_margin_db / 3.0)

        # 限制在硬件上限内
        rate_gbps = min(rate_gbps, self.max_rate_gbps)
        rate_mbps = rate_gbps * 1e3  # Gbps -> Mbps

        # 速率低于最低可用阈值时置 0
        if rate_mbps < MIN_USABLE_RATE_MBPS:
            rate_mbps = 0.0

        total_loss_db = -geometric_loss_db + pointing_loss_db + misc_loss_db

        return LaserISLResult(
            is_visible=True,
            distance_km=dist_km,
            fspl_db=fspl_db,
            geometric_loss_db=-geometric_loss_db,  # 转为正数表示损耗量
            pointing_loss_db=pointing_loss_db,
            total_loss_db=total_loss_db,
            tx_power_dbw=tx_power_dbw,
            received_power_dbw=received_power_dbw,
            sensitivity_dbw=sensitivity_dbw,
            link_margin_db=link_margin_db,
            rate_mbps=rate_mbps,
        )


# ═══════════════════════════════════════════════════════════════
#  地球遮挡判定（视线可见性）
# ═══════════════════════════════════════════════════════════════

def check_los_visibility(
    sat1_pos: Dict[str, float],
    sat2_pos: Dict[str, float],
    earth_a_km: float = EARTH_A_KM,
    earth_b_km: float = EARTH_B_KM,
) -> bool:
    """检验两颗卫星之间视线是否被地球遮挡（WGS-84 椭球）。

    采用椭球参数方程求解直线与椭球的交点：将地球缩放为标准单位球，
    在缩放坐标系中判断线段是否与单位球相交。

    Parameters
    ----------
    sat1_pos : dict
        卫星1位置，含 ``lat``（度）、``lon``（度）、``alt``（米）。
    sat2_pos : dict
        卫星2位置，含 ``lat``（度）、``lon``（度）、``alt``（米）。
    earth_a_km : float
        地球椭球长半轴 (km)，默认 WGS-84。
    earth_b_km : float
        地球椭球短半轴（极轴方向）(km)，默认 WGS-84。

    Returns
    -------
    bool
        True 表示视线不被地球遮挡（两星可见），False 表示视线穿越地球（被遮挡）。
    """
    # 卫星 ECEF 坐标 (km)
    x1, y1, z1 = lla_to_ecef(sat1_pos["lat"], sat1_pos["lon"], sat1_pos["alt"])
    x2, y2, z2 = lla_to_ecef(sat2_pos["lat"], sat2_pos["lon"], sat2_pos["alt"])

    # 将椭球缩放为单位球：x,y 轴除以 a，z 轴除以 b
    # 在缩放坐标系中判断直线段与单位球的交叉
    ax, ay, az = x1 / earth_a_km, y1 / earth_a_km, z1 / earth_b_km
    bx, by, bz = x2 / earth_a_km, y2 / earth_a_km, z2 / earth_b_km

    # 参数直线：P(t) = A + t·(B - A)，t ∈ [0, 1]
    dx = bx - ax
    dy = by - ay
    dz = bz - az

    # 求解 |P(t)|² = 1 即 at² + bt + c = 0
    a_coef = dx * dx + dy * dy + dz * dz
    b_coef = 2.0 * (ax * dx + ay * dy + az * dz)
    c_coef = ax * ax + ay * ay + az * az - 1.0

    if a_coef < 1e-30:
        # 两星几乎重合，认为可见
        return True

    discriminant = b_coef * b_coef - 4.0 * a_coef * c_coef

    if discriminant < 0:
        # 直线不与椭球相交 → 视线不被遮挡
        return True

    # 存在交点，计算参数 t1, t2
    sqrt_disc = math.sqrt(discriminant)
    t1 = (-b_coef - sqrt_disc) / (2.0 * a_coef)
    t2 = (-b_coef + sqrt_disc) / (2.0 * a_coef)

    # 若两个交点均在 t ∈ (0, 1) 范围内，说明线段穿越地球内部 → 被遮挡
    # 留出小数值容差避免卫星轨道刚好在表面时误判
    eps = 1e-6
    if t1 > eps and t2 < 1.0 - eps:
        return False  # 视线被地球遮挡

    return True


# ═══════════════════════════════════════════════════════════════
#  便捷接口（供 orbit.py / core.py 调用）
# ═══════════════════════════════════════════════════════════════

# 模块级默认模型实例，可被外部调用方复用（线程安全：无状态计算）
_DEFAULT_MODEL = LaserISLModel()


def laser_isl_rate(
    sat1_pos: Dict[str, float],
    sat2_pos: Dict[str, float],
    model: Optional[LaserISLModel] = None,
) -> float:
    """计算两颗卫星之间的激光 ISL 可达速率 (Mbps)。

    包含地球遮挡判定：当视线被地球遮挡时返回 0.0。

    Parameters
    ----------
    sat1_pos : dict
        卫星1位置，含 ``lat``、``lon``（度）、``alt``（米）。
    sat2_pos : dict
        卫星2位置，含 ``lat``、``lon``（度）、``alt``（米）。
    model : LaserISLModel, optional
        自定义激光 ISL 模型；不提供则使用默认模型。

    Returns
    -------
    float
        可达数据率 (Mbps)；视线被遮挡或链路预算不足时返回 0.0。
    """
    m = model or _DEFAULT_MODEL
    result = m.compute(sat1_pos, sat2_pos)
    return result.rate_mbps


def laser_isl_check(
    sat1_pos: Dict[str, float],
    sat2_pos: Dict[str, float],
) -> bool:
    """判断两颗卫星之间是否存在激光 ISL 几何可见性（视线不被地球遮挡）。

    Parameters
    ----------
    sat1_pos, sat2_pos : dict
        卫星位置，含 ``lat``、``lon``（度）、``alt``（米）。

    Returns
    -------
    bool
        True 表示可见，False 表示视线被地球遮挡。
    """
    return check_los_visibility(sat1_pos, sat2_pos)


# ═══════════════════════════════════════════════════════════════
#  私有辅助函数
# ═══════════════════════════════════════════════════════════════

def _distance_km(pos1: Dict[str, float], pos2: Dict[str, float]) -> float:
    """计算两颗卫星之间的三维欧氏距离 (km)。"""
    x1, y1, z1 = lla_to_ecef(pos1["lat"], pos1["lon"], pos1["alt"])
    x2, y2, z2 = lla_to_ecef(pos2["lat"], pos2["lon"], pos2["alt"])
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2 + (z2 - z1) ** 2)
