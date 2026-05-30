# -*- coding: utf-8 -*-
"""链路预算引擎（Link Budget Engine）。

按照 ITU-R / DVB-S2 标准实现卫星通信链路预算分析：

- **FSPL**：自由空间路径损耗，FSPL(dB) = 20·log10(4πd/λ)
- **C/N0**：载噪比功率密度
- **Eb/N0**：比特能量噪声密度比
- **SNR**：信噪比
- **BER**：对 QPSK / 8PSK / 16APSK 给出误码率估算
- **可达速率**：香农容量与调制约束下的可达 Mbps
- **大气衰减**：雨衰（ITU-R P.838）与气体吸收（ITU-R P.676）叠加损耗

天线参数默认值基于中国天链二号 Ka 频段与典型 X 频段参数。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal, Optional

# ───────────────────────── 物理常数 ─────────────────────────
BOLTZMANN_DB = -228.6  # dBW/K/Hz  (10·log10(1.380649e-23))
SPEED_OF_LIGHT = 2.998e8  # m/s

# ────────────────── 频段中心频率 (Hz) ──────────────────────
FREQUENCY_TABLE: dict[str, float] = {
    "Ka": 26.5e9,   # Ka 频段上行中心 26.5 GHz
    "X":  8.4e9,    # X  频段中心 8.4 GHz
    "Ku": 14.0e9,   # Ku 频段中心 14 GHz
    "S":  2.1e9,    # S  频段中心 2.1 GHz
    "L":  1.5e9,    # L  频段中心 1.5 GHz
    "ISL": 60.0e9,  # 星间链路 60 GHz (毫米波 ISL)
}

# ──────────────────── 调制方式信息 ─────────────────────────
ModScheme = Literal["QPSK", "8PSK", "16APSK", "BPSK"]

MODULATION_BITS: dict[ModScheme, int] = {
    "BPSK":   1,
    "QPSK":   2,
    "8PSK":   3,
    "16APSK": 4,
}

# DVB-S2 典型代码率；用于香农/调制约束可达速率
MODULATION_CODE_RATE: dict[ModScheme, float] = {
    "BPSK":   3 / 4,
    "QPSK":   3 / 4,
    "8PSK":   2 / 3,
    "16APSK": 3 / 4,
}

# BER 阈值 Eb/N0 (dB)，近似 BER≤1e-6 时的 Eb/N0
MODULATION_EBNON_THRESHOLD_DB: dict[ModScheme, float] = {
    "BPSK":   10.5,
    "QPSK":   10.5,
    "8PSK":   14.0,
    "16APSK": 17.5,
}

# ──────────────────── 典型天线参数 ─────────────────────────
# EIRP (dBW) 典型值：LEO 卫星对地面站
EIRP_DEFAULTS: dict[str, float] = {
    "Ka": 45.0,   # Ka 频段 LEO → GS (dBW)
    "X":  38.0,   # X  频段 LEO → GS (dBW)
    "Ku": 42.0,   # Ku 频段 LEO → GS (dBW)
    "ISL": 55.0,  # GEO 星间 ISL  (dBW)
}

# G/T (dB/K)：地面接收站系统品质因数
G_T_DEFAULTS: dict[str, float] = {
    "Ka": 25.0,   # Ka 频段大口径碟形天线 (dB/K)
    "X":  20.0,   # X  频段中等口径天线 (dB/K)
    "Ku": 22.0,   # Ku 频段天线 (dB/K)
    "ISL": 30.0,  # GEO 星间大增益天线 (dB/K)
}

# 噪声带宽 (MHz) 典型值
BANDWIDTH_DEFAULTS: dict[str, float] = {
    "Ka": 500.0,  # Ka 频段 500 MHz
    "X":  40.0,   # X  频段 40 MHz
    "Ku": 200.0,  # Ku 频段 200 MHz
    "ISL": 1000.0,# 星间链路 1 GHz
}

# 附加系统损耗 (dB)：大气吸收、雨衰、极化损失、指向误差等
MISC_LOSSES_DB: dict[str, float] = {
    "Ka": 2.5,   # Ka 频段雨衰等损耗较大
    "X":  1.0,
    "Ku": 1.8,
    "ISL": 0.3,
}


# ═══════════════════════════════════════════════════════════════
#  数据类
# ═══════════════════════════════════════════════════════════════

@dataclass
class LinkBudgetResult:
    """链路预算计算结果（全部 dB/dBW 量纲除非特别注明）。"""

    # 输入几何
    distance_km: float          # 斜距 (km)
    frequency_hz: float         # 载波频率 (Hz)
    band: str                   # 频段名称

    # 路径损耗
    fspl_db: float              # 自由空间路径损耗 FSPL (dB)
    total_loss_db: float        # 总路径损耗 = FSPL + 杂散 (dB)

    # 链路参数
    eirp_dbw: float             # 有效全向辐射功率 (dBW)
    g_t_db_k: float             # 接收 G/T (dB/K)
    bandwidth_hz: float         # 噪声带宽 (Hz)

    # 载噪比
    cn0_db_hz: float            # C/N0 (dBHz)
    snr_db: float               # SNR = C/N0 - 10·log10(BW) (dB)
    ebn0_db: float              # Eb/N0 (dB)，以最大可达速率计算

    # 调制与 BER
    modulation: str             # 推荐调制方式
    ber: float                  # 误码率估算（线性）
    ber_log10: float            # log10(BER)

    # 可达速率
    shannon_capacity_mbps: float  # 香农容量 (Mbps)
    achievable_rate_mbps: float   # 调制+编码约束可达速率 (Mbps)

    def to_dict(self) -> dict:
        return {
            "distance_km": round(self.distance_km, 3),
            "frequency_hz": self.frequency_hz,
            "band": self.band,
            "fspl_db": round(self.fspl_db, 2),
            "total_loss_db": round(self.total_loss_db, 2),
            "eirp_dbw": round(self.eirp_dbw, 2),
            "g_t_db_k": round(self.g_t_db_k, 2),
            "bandwidth_hz": self.bandwidth_hz,
            "cn0_db_hz": round(self.cn0_db_hz, 2),
            "snr_db": round(self.snr_db, 2),
            "ebn0_db": round(self.ebn0_db, 2),
            "modulation": self.modulation,
            "ber": self.ber,
            "ber_log10": round(self.ber_log10, 2),
            "shannon_capacity_mbps": round(self.shannon_capacity_mbps, 3),
            "achievable_rate_mbps": round(self.achievable_rate_mbps, 3),
        }


@dataclass
class LinkBudget:
    """链路预算引擎配置。

    参数
    ----
    band : str
        频段名称，决定频率、默认 EIRP/G-T/带宽等。
    eirp_dbw : float, optional
        发射端有效全向辐射功率 (dBW)。不设则取频段默认值。
    g_t_db_k : float, optional
        接收端系统 G/T (dB/K)。不设则取频段默认值。
    bandwidth_mhz : float, optional
        噪声带宽 (MHz)。不设则取频段默认值。
    misc_loss_db : float, optional
        附加系统杂散损耗 (dB)（大气、雨衰、指向等）。
    frequency_hz : float, optional
        覆盖频段默认频率。
    """

    band: str = "Ka"
    eirp_dbw: Optional[float] = None
    g_t_db_k: Optional[float] = None
    bandwidth_mhz: Optional[float] = None
    misc_loss_db: Optional[float] = None
    frequency_hz: Optional[float] = None

    def __post_init__(self) -> None:
        if self.band not in FREQUENCY_TABLE:
            raise ValueError(f"Unsupported band '{self.band}'. "
                             f"Supported: {list(FREQUENCY_TABLE)}")
        if self.frequency_hz is None:
            self.frequency_hz = FREQUENCY_TABLE[self.band]
        if self.eirp_dbw is None:
            self.eirp_dbw = EIRP_DEFAULTS.get(self.band, 40.0)
        if self.g_t_db_k is None:
            self.g_t_db_k = G_T_DEFAULTS.get(self.band, 20.0)
        if self.bandwidth_mhz is None:
            self.bandwidth_mhz = BANDWIDTH_DEFAULTS.get(self.band, 100.0)
        if self.misc_loss_db is None:
            self.misc_loss_db = MISC_LOSSES_DB.get(self.band, 1.0)

    # ────────────────── 主计算入口 ──────────────────────────
    def compute(self, distance_km: float) -> LinkBudgetResult:
        """计算给定斜距下的完整链路预算。

        Parameters
        ----------
        distance_km : float
            发射端到接收端斜距 (km)。

        Returns
        -------
        LinkBudgetResult
        """
        if distance_km <= 0:
            raise ValueError(f"distance_km must be positive, got {distance_km}")

        bw_hz = self.bandwidth_mhz * 1e6

        # 1. 自由空间路径损耗
        fspl = compute_fspl_db(distance_km * 1e3, self.frequency_hz)  # type: ignore[arg-type]

        # 2. 总路径损耗
        total_loss = fspl + self.misc_loss_db  # type: ignore[operator]

        # 3. C/N0 (dBHz)
        cn0 = compute_cn0(
            eirp_dbw=self.eirp_dbw,          # type: ignore[arg-type]
            total_loss_db=total_loss,
            g_t_db_k=self.g_t_db_k,          # type: ignore[arg-type]
        )

        # 4. SNR (dB) = C/N0 - 10·log10(BW)
        snr = cn0 - 10.0 * math.log10(bw_hz)

        # 5. 香农容�� (Mbps)
        shannon_mbps = compute_capacity_mbps(snr_db=snr, bandwidth_hz=bw_hz)

        # 6. 选择调制方式（贪心：Eb/N0 刚好满足门限的最高阶）
        modulation = _select_modulation(cn0=cn0, bandwidth_hz=bw_hz)
        bits_per_symbol = MODULATION_BITS[modulation]
        code_rate = MODULATION_CODE_RATE[modulation]

        # 7. 调制约束可达速率
        achievable_mbps = _achievable_rate_mbps(
            cn0_db_hz=cn0,
            bandwidth_hz=bw_hz,
            bits_per_symbol=bits_per_symbol,
            code_rate=code_rate,
            shannon_mbps=shannon_mbps,
        )

        # 8. Eb/N0（以可达速率换算）
        ebn0 = compute_ebn0(cn0_db_hz=cn0, rate_bps=max(achievable_mbps * 1e6, 1.0))

        # 9. BER
        ber_val = compute_ber(ebn0_db=ebn0, modulation=modulation)
        ber_log10 = math.log10(max(ber_val, 1e-15))

        return LinkBudgetResult(
            distance_km=distance_km,
            frequency_hz=float(self.frequency_hz),   # type: ignore[arg-type]
            band=self.band,
            fspl_db=fspl,
            total_loss_db=total_loss,
            eirp_dbw=float(self.eirp_dbw),           # type: ignore[arg-type]
            g_t_db_k=float(self.g_t_db_k),           # type: ignore[arg-type]
            bandwidth_hz=bw_hz,
            cn0_db_hz=cn0,
            snr_db=snr,
            ebn0_db=ebn0,
            modulation=modulation,
            ber=ber_val,
            ber_log10=ber_log10,
            shannon_capacity_mbps=shannon_mbps,
            achievable_rate_mbps=achievable_mbps,
        )


# ═══════════════════════════════════════════════════���═══════════
#  纯函数（可独立导入）
# ═══════════════════════════════════════════════════════════════

def compute_fspl_db(distance_m: float, frequency_hz: float) -> float:
    """自由空间路径损耗 (dB)。

    FSPL = 20·log10(4π·d·f / c)

    Parameters
    ----------
    distance_m : float
        斜距（米）。
    frequency_hz : float
        载波频率（Hz）。

    Returns
    -------
    float
        FSPL，单位 dB（正数，代表损耗）。
    """
    if distance_m <= 0 or frequency_hz <= 0:
        raise ValueError("distance_m and frequency_hz must be positive.")
    return 20.0 * math.log10(4.0 * math.pi * distance_m * frequency_hz / SPEED_OF_LIGHT)


def compute_cn0(eirp_dbw: float, total_loss_db: float, g_t_db_k: float) -> float:
    """计算 C/N0 (dBHz)。

    C/N0 = EIRP(dBW) - L(dB) + G/T(dB/K) - k(dBW/K/Hz)

    Parameters
    ----------
    eirp_dbw : float
        发射 EIRP (dBW)。
    total_loss_db : float
        总路径损耗 (dB)。
    g_t_db_k : float
        接收端 G/T (dB/K)。

    Returns
    -------
    float
        C/N0 (dBHz)。
    """
    return eirp_dbw - total_loss_db + g_t_db_k - BOLTZMANN_DB


def compute_ebn0(cn0_db_hz: float, rate_bps: float) -> float:
    """由 C/N0 与信息速率计算 Eb/N0 (dB)。

    Eb/N0 = C/N0 - 10·log10(Rb)

    Parameters
    ----------
    cn0_db_hz : float
        C/N0 (dBHz)。
    rate_bps : float
        信息速率（比特/秒）。

    Returns
    -------
    float
        Eb/N0 (dB)。
    """
    if rate_bps <= 0:
        raise ValueError("rate_bps must be positive.")
    return cn0_db_hz - 10.0 * math.log10(rate_bps)


def compute_ber(ebn0_db: float, modulation: ModScheme = "QPSK") -> float:  # type: ignore[assignment]
    """BER 近似估算（AWGN 信道，无编码）。

    - BPSK / QPSK: BER = Q(√(2·Eb/N0))  ≈ 0.5·erfc(√(Eb/N0))
    - 8PSK       : BER ≈ (2/3)·erfc(√(Eb/N0·sin²(π/8)))
    - 16APSK     : BER ≈ (1/2)·erfc(√(Eb/N0 / (2·log2(16))))

    Parameters
    ----------
    ebn0_db : float
        Eb/N0 (dB)。
    modulation : ModScheme
        调制方式。

    Returns
    -------
    float
        误码率（0–1 之间的线性值）。
    """
    ebn0_lin = 10.0 ** (ebn0_db / 10.0)

    if modulation in ("BPSK", "QPSK"):
        ber = 0.5 * math.erfc(math.sqrt(ebn0_lin))
    elif modulation == "8PSK":
        # 近似：BER ≈ (2/3)·erfc(√(Eb/N0·sin²(π/8)))
        arg = math.sqrt(ebn0_lin * math.sin(math.pi / 8) ** 2)
        ber = (2.0 / 3.0) * 0.5 * math.erfc(arg)
    elif modulation == "16APSK":
        # 近似：BER ≈ (1/4)·erfc(√(Eb/N0 / (2·log2(16)/2)))
        arg = math.sqrt(ebn0_lin / (0.5 * math.log2(16)))
        ber = 0.25 * math.erfc(arg)
    else:
        raise ValueError(f"Unknown modulation '{modulation}'.")

    return max(ber, 1e-15)


def compute_capacity_mbps(snr_db: float, bandwidth_hz: float) -> float:
    """香农信道容量 (Mbps)。

    C = BW · log2(1 + SNR)

    Parameters
    ----------
    snr_db : float
        信噪比 (dB)。
    bandwidth_hz : float
        带宽 (Hz)。

    Returns
    -------
    float
        香农容量 (Mbps)。
    """
    snr_lin = 10.0 ** (snr_db / 10.0)
    capacity_bps = bandwidth_hz * math.log2(1.0 + snr_lin)
    return capacity_bps / 1e6


# ═══════════════════════════════════════════════════════════════
#  便捷链路预算函数（供 orbit.py / core.py 调用）
# ═══════════════════════════════════════════════════════════════

def link_budget_direct(
    distance_km: float,
    antenna_type: str = "Ka",
    data_type: Optional[str] = None,
    elevation_deg: float = 45.0,
    rainfall_rate_mm_h: float = 0.0,
    gs_altitude_km: float = 0.0,
) -> LinkBudgetResult:
    """LEO 卫星→地面站直连链路预算。

    Parameters
    ----------
    distance_km : float
        LEO 卫星到地面站斜距 (km)。
    antenna_type : str
        地面站天线频段（"Ka" / "X" 等）。
    data_type : str, optional
        数据类型（"RAW_IMAGE" 时对速率做 0.6 折调整）。
    elevation_deg : float
        卫星仰角（度），用于大气衰减计算，默认 45°。
    rainfall_rate_mm_h : float
        地面降雨率（mm/h），0 表示晴天无雨衰，默认 0。
    gs_altitude_km : float
        地面站海拔（km），用于雨衰路径折算，默认 0。

    Returns
    -------
    LinkBudgetResult
    """
    from backend.comms.atmosphere import atmospheric_loss_for_link

    band = antenna_type if antenna_type in FREQUENCY_TABLE else "Ka"
    freq_hz = FREQUENCY_TABLE[band]

    # 计算大气衰减（雨衰 + 气体吸收），作为附加 misc_loss 叠加
    atm_loss_db = atmospheric_loss_for_link(
        freq_hz=freq_hz,
        elevation_deg=max(elevation_deg, 0.1),
        rainfall_rate_mm_h=rainfall_rate_mm_h,
        gs_altitude_km=gs_altitude_km,
    )

    lb = LinkBudget(band=band)
    # 将大气衰减叠加到杂散损耗之上
    lb.misc_loss_db = (lb.misc_loss_db or 0.0) + atm_loss_db  # type: ignore[operator]
    result = lb.compute(distance_km)

    if data_type == "RAW_IMAGE":
        # RAW_IMAGE 占用更高的带宽开销，效率折扣 0.6
        result.achievable_rate_mbps *= 0.6
        result.shannon_capacity_mbps *= 0.6

    return result


def link_budget_relay(
    dist_leo_geo_km: float,
    dist_geo_gs_km: float,
    data_type: Optional[str] = None,
    elevation_deg_gs: float = 45.0,
    rainfall_rate_mm_h: float = 0.0,
    gs_altitude_km: float = 0.0,
) -> LinkBudgetResult:
    """LEO→GEO→地面站中继链路预算（返回瓶颈链路结果）。

    Parameters
    ----------
    dist_leo_geo_km : float
        LEO 到 GEO 斜距 (km)。
    dist_geo_gs_km : float
        GEO 到地面站斜距 (km)。
    data_type : str, optional
        数据类型。
    elevation_deg_gs : float
        地面站观测 GEO 的仰角（度），用于下行链路大气衰减，默认 45°。
    rainfall_rate_mm_h : float
        地面降雨率（mm/h），影响地面站侧链路，默认 0。
    gs_altitude_km : float
        地面站海拔（km），默认 0。

    Returns
    -------
    LinkBudgetResult
        瓶颈链路（可达速率最低）的链路预算结果。
    """
    from backend.comms.atmosphere import atmospheric_loss_for_link

    freq_ka_hz = FREQUENCY_TABLE["Ka"]

    # LEO→GEO 上行（Ka 频段）：大气衰减按 LEO 仰角近似（LEO 距地面 ~500 km，与 GEO 近乎天顶角）
    # 上行链路大气衰减影响小（星间链路不穿雨层），使用气体��收（零雨衰）
    atm_loss_up_db = atmospheric_loss_for_link(
        freq_hz=freq_ka_hz,
        elevation_deg=70.0,   # LEO→GEO：高仰角，路径穿越大气层短
        rainfall_rate_mm_h=0.0,
    )
    lb_up = LinkBudget(
        band="Ka",
        eirp_dbw=EIRP_DEFAULTS["Ka"] + 3,
        g_t_db_k=G_T_DEFAULTS["Ka"] + 5,
        misc_loss_db=MISC_LOSSES_DB.get("Ka", 2.5) + atm_loss_up_db,
    )
    res_up = lb_up.compute(dist_leo_geo_km)

    # GEO→地面站下行（Ka 频段）：叠加地面站仰角与降雨率对应的大气衰减
    atm_loss_dn_db = atmospheric_loss_for_link(
        freq_hz=freq_ka_hz,
        elevation_deg=max(elevation_deg_gs, 0.1),
        rainfall_rate_mm_h=rainfall_rate_mm_h,
        gs_altitude_km=gs_altitude_km,
    )
    lb_dn = LinkBudget(
        band="Ka",
        misc_loss_db=MISC_LOSSES_DB.get("Ka", 2.5) + atm_loss_dn_db,
    )
    res_dn = lb_dn.compute(dist_geo_gs_km)

    # 瓶颈取速率最��者
    bottleneck = res_up if res_up.achievable_rate_mbps < res_dn.achievable_rate_mbps else res_dn
    if data_type == "RAW_IMAGE":
        bottleneck.achievable_rate_mbps *= 0.6
        bottleneck.shannon_capacity_mbps *= 0.6
    return bottleneck


def link_budget_inter_satellite(distance_km: float) -> LinkBudgetResult:
    """GEO 星间链路（ISL）链路预算。

    Parameters
    ----------
    distance_km : float
        两颗 GEO 卫星之间距离 (km)。

    Returns
    -------
    LinkBudgetResult
    """
    lb = LinkBudget(band="ISL")
    return lb.compute(distance_km)


# ═══════════════════════════════════════════════════════════════
#  私有辅助
# ═══════════════════════════════════════════════════════════════

def _select_modulation(cn0: float, bandwidth_hz: float) -> ModScheme:  # type: ignore[return]
    """根据 C/N0 和带宽，贪心选择可满足 BER≤1e-6 的最高阶调制方式。

    遍历顺序从高阶到低阶，返回首个 Eb/N0 超过门限的调制方式；
    若均不满足则降级到 BPSK。
    """
    candidates: list[ModScheme] = ["16APSK", "8PSK", "QPSK", "BPSK"]  # type: ignore[assignment]
    for mod in candidates:
        bits = MODULATION_BITS[mod]
        code_rate = MODULATION_CODE_RATE[mod]
        # ���调制+编码约束速率计算 Eb/N0
        rate_bps = bandwidth_hz * bits * code_rate
        ebn0 = cn0 - 10.0 * math.log10(max(rate_bps, 1.0))
        threshold = MODULATION_EBNON_THRESHOLD_DB[mod]
        if ebn0 >= threshold:
            return mod
    return "BPSK"


def _achievable_rate_mbps(
    cn0_db_hz: float,
    bandwidth_hz: float,
    bits_per_symbol: int,
    code_rate: float,
    shannon_mbps: float,
) -> float:
    """调制+编码约束的可达速率 (Mbps)。

    取香农容量与调制硬约束的最小值，保证不超物理上限。
    """
    # 调制约束：BW × bits_per_symbol × code_rate
    modulation_limit_mbps = bandwidth_hz * bits_per_symbol * code_rate / 1e6
    return min(shannon_mbps, modulation_limit_mbps)
