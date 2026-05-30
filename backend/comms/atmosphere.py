# -*- coding: utf-8 -*-
"""大气衰减模型 — 雨衰与气体吸收（ITU-R P.838/P.618 简化）。

实现两类额外路径损耗，作为附加 dB 项叠加进链路预算：

1. **雨衰**（Rain Attenuation）— ITU-R P.838 / P.618
   - 比雨衰系数 γ_R (dB/km) 由频率、降雨率 R₀.₀₁ 查表得到
   - 有效路径长度按 P.618 余弦/仰角缩减系数折算
   - 结果为给定超越概率下的雨衰 A_rain (dB)

2. **气体吸收衰减**（Gaseous Attenuation）— ITU-R P.676 极简近似
   - 氧气吸收峰（60 GHz 附近）与水汽吸收（22.2 GHz 附近）
   - 给出路径等效气体吸收 A_gas (dB)

合并函数 ``total_atmospheric_loss_db`` 返回雨衰 + 气体吸收之和，
供链路预算引擎注入 ``misc_loss_db``。

参考文献
---------
- ITU-R Rec. P.838-3: Specific attenuation model for rain
- ITU-R Rec. P.618-13: Propagation data for Earth-space paths
- ITU-R Rec. P.676-12: Attenuation by atmospheric gases
"""
from __future__ import annotations

import math
from typing import Optional

# ───────────────────────────── 常量 ─────────────────────────────

# 等效雨层高度 (km) — ITU-R P.839-4 全球均值
_RAIN_HEIGHT_KM = 4.0   # 0°C 等温线高度，典型中纬度值

# 标准大气水汽含量 (g/m³)
_STD_WATER_VAPOR_DENSITY = 7.5   # 对应 RH≈60% @ 15°C 的标准大气

# 标准大气氧气比密度 (g/m³)
_STD_OXYGEN_DENSITY = 1.3e3     # 近似海平面氧气密度 (g/m³ equiv)

# ───────────────── ITU-R P.838-3 雨衰系数查表 ──────────────────
# 对于水平极化（H-pol）与垂直极化（V-pol）平均值（圆极化近似）：
#   γ_R = k · R^α  (dB/km)，其中 R 单位 mm/h
#
# 频率 (GHz) → (k_H, α_H, k_V, α_V) 参考 P.838-3 Table 1-2
# 以下取 10 个代表性频点（对数插值使用）
_P838_TABLE: list[tuple[float, float, float, float, float]] = [
    # (freq_ghz, k_H,    α_H,  k_V,    α_V)
    (1.0,   0.0000387, 0.912, 0.0000352, 0.880),
    (2.0,   0.000154,  0.963, 0.000138,  0.923),
    (4.0,   0.000650,  1.121, 0.000591,  1.075),
    (6.0,   0.00175,   1.308, 0.00155,   1.265),
    (7.0,   0.00301,   1.332, 0.00265,   1.312),
    (8.0,   0.00454,   1.327, 0.00395,   1.310),
    (10.0,  0.0101,    1.276, 0.00887,   1.264),
    (12.0,  0.0188,    1.217, 0.0168,    1.200),
    (15.0,  0.0367,    1.154, 0.0335,    1.128),
    (20.0,  0.0751,    1.099, 0.0691,    1.065),
    (25.0,  0.124,     1.061, 0.113,     1.030),
    (30.0,  0.187,     1.021, 0.167,     1.000),
    (35.0,  0.263,     0.979, 0.233,     0.963),
    (40.0,  0.350,     0.939, 0.310,     0.929),
    (50.0,  0.536,     0.873, 0.479,     0.868),
    (60.0,  0.707,     0.826, 0.642,     0.824),
    (70.0,  0.851,     0.793, 0.784,     0.793),
    (80.0,  0.975,     0.769, 0.906,     0.769),
    (100.0, 1.06,      0.753, 0.999,     0.754),
]


def _interp_p838(freq_ghz: float) -> tuple[float, float]:
    """在 P.838 表格中按对数插值求 (k, α)（H/V 极化平均）。

    Returns
    -------
    (k, alpha) : tuple[float, float]
        比雨衰系数 k 和指数 α，用于 γ_R = k · R^α。
    """
    table = _P838_TABLE
    if freq_ghz <= table[0][0]:
        k_h, a_h, k_v, a_v = table[0][1], table[0][2], table[0][3], table[0][4]
        return (k_h + k_v) / 2.0, (a_h + a_v) / 2.0
    if freq_ghz >= table[-1][0]:
        k_h, a_h, k_v, a_v = table[-1][1], table[-1][2], table[-1][3], table[-1][4]
        return (k_h + k_v) / 2.0, (a_h + a_v) / 2.0

    # 找到插值区间（按对数频率）
    lf = math.log10(freq_ghz)
    for i in range(len(table) - 1):
        f_lo, f_hi = table[i][0], table[i + 1][0]
        if f_lo <= freq_ghz <= f_hi:
            t = (lf - math.log10(f_lo)) / (math.log10(f_hi) - math.log10(f_lo))
            # k 按对数插值，α 按线性插值（P.838 推荐）
            k_h = 10.0 ** (math.log10(table[i][1]) + t * (math.log10(table[i + 1][1]) - math.log10(table[i][1])))
            k_v = 10.0 ** (math.log10(table[i][3]) + t * (math.log10(table[i + 1][3]) - math.log10(table[i][3])))
            a_h = table[i][2] + t * (table[i + 1][2] - table[i][2])
            a_v = table[i][4] + t * (table[i + 1][4] - table[i][4])
            return (k_h + k_v) / 2.0, (a_h + a_v) / 2.0

    # fallback
    k_h, a_h, k_v, a_v = table[-1][1], table[-1][2], table[-1][3], table[-1][4]
    return (k_h + k_v) / 2.0, (a_h + a_v) / 2.0


def rain_attenuation_db(
    freq_hz: float,
    elevation_deg: float,
    rainfall_rate_mm_h: float,
    gs_altitude_km: float = 0.0,
) -> float:
    """计算雨衰 A_rain (dB)，按 ITU-R P.618-13 / P.838-3 简化方法。

    方法
    ----
    1. 查 P.838 表得比雨衰系数 k、α。
    2. 计算比雨衰 γ_R = k · R^α (dB/km)。
    3. 等效斜路径长度 L_s = (h_rain - h_gs) / sin(θ)，
       有效路径长度 L_e = L_s · r（P.618 缩减系数 r）。
    4. 雨衰 A_rain = γ_R · L_e (dB)。

    Parameters
    ----------
    freq_hz : float
        载波频率（Hz）。
    elevation_deg : float
        卫星仰角（度），范围 [0°, 90°]。
    rainfall_rate_mm_h : float
        地面降雨率 R₀.₀₁（mm/h），即超越概率 0.01% 的降雨率。
        典型值：轻雨 ≈ 5, 中雨 ≈ 12, 大雨 ≈ 25, 暴雨 ≈ 50。
    gs_altitude_km : float
        地面站海拔高度（km），默认 0 km（海平面）。

    Returns
    -------
    float
        雨衰 A_rain (dB)，非负值；零降雨率时返回 0。
    """
    if rainfall_rate_mm_h <= 0.0:
        return 0.0

    freq_ghz = freq_hz / 1e9
    k, alpha = _interp_p838(freq_ghz)

    # 比雨衰 γ_R (dB/km)
    gamma_r = k * (rainfall_rate_mm_h ** alpha)

    # 有效雨层高度（地面站海拔之上的雨层厚度）
    h_rain_above_gs = max(_RAIN_HEIGHT_KM - gs_altitude_km, 0.1)  # km

    # 仰角夹紧，避免极低仰角除以零
    elev_rad = math.radians(max(elevation_deg, 0.1))

    # 斜路径长度 L_s (km)
    if elevation_deg >= 5.0:
        l_s = h_rain_above_gs / math.sin(elev_rad)
    else:
        # 低仰角：用弦长近似（P.618 附录 1 低仰角公式）
        cos_el = math.cos(elev_rad)
        R_e = 6371.0   # 地球半径 km
        l_s = (2.0 * h_rain_above_gs) / (
            math.sqrt(math.sin(elev_rad) ** 2 + 2.0 * h_rain_above_gs / R_e)
            + math.sin(elev_rad)
        )

    # 水平投影距离 L_G (km)
    l_g = l_s * math.cos(elev_rad)

    # P.618 缩减系数 r₀.₀₁（针对 0.01% 超越概率）
    r_001 = 1.0 / (1.0 + 0.78 * math.sqrt(l_g * gamma_r / freq_ghz) - 0.38 * (1.0 - math.exp(-2.0 * l_g)))

    # 仰角调整因子 ζ
    zeta_num = math.degrees(math.atan2(h_rain_above_gs - gs_altitude_km, l_g * r_001))
    if zeta_num > elevation_deg:
        l_r = l_g * r_001 / math.cos(elev_rad)
        chi = 36.0 - abs(gs_altitude_km)   # 纬度修正因子（简化：用地面站纬度替代，此处取均值）
        chi = max(0.0, chi)                  # 夹紧 ≥ 0
    else:
        l_r = h_rain_above_gs / math.sin(elev_rad)
        chi = 0.0

    v_001 = 31.0 * (1.0 - math.exp(-(elevation_deg / (1.0 + chi)))) * math.sqrt(l_r * gamma_r) / freq_ghz ** 2 - 0.45
    v_001 = max(v_001, 0.0)
    l_e = l_r * min(r_001, 1.0 / (1.0 + v_001 * r_001))  # 有效路径长度 (km)

    a_rain = gamma_r * max(l_e, 0.0)
    return max(a_rain, 0.0)


def gaseous_attenuation_db(
    freq_hz: float,
    elevation_deg: float,
    water_vapor_density_g_m3: float = _STD_WATER_VAPOR_DENSITY,
    scale_height_km: float = 2.0,
) -> float:
    """计算大气气体吸收衰减 A_gas (dB)，按 ITU-R P.676-12 极简模型。

    包含两个主吸收分量：
    - 氧气 (O₂)：Zennith 特征衰减约 0.005–0.008 dB/km（1–40 GHz），60 GHz 附近强吸收峰
    - 水汽 (H₂O)：22.235 GHz 共振峰与宽带连续谱

    斜路径等效地平天顶折算：A_gas = γ_total · h_eff / sin(θ)

    Parameters
    ----------
    freq_hz : float
        载波频率（Hz）。
    elevation_deg : float
        卫星仰角（度）。
    water_vapor_density_g_m3 : float
        地面水汽密度（g/m³），默认 7.5（标准大气）。
    scale_height_km : float
        等效大气标高（km），默认 2.0 km（水汽标高）。

    Returns
    -------
    float
        气体吸收衰减 A_gas (dB)，非负值。
    """
    f_ghz = freq_hz / 1e9

    # ── 氧气比衰减 γ_O (dB/km) ── 极简单色单峰近似 ──
    # 60 GHz 附近强吸收：简化 Van Vleck-Weisskopf 单峰 Lorentz 线型
    _f_O2 = 60.0   # 氧气 60 GHz 吸收复合带中心 GHz
    _gamma_O2_peak = 14.0  # 60 GHz 峰值比衰减 (dB/km)，近似值
    _df_O2 = 10.0  # 半峰全宽 GHz（简化）
    gamma_O2 = _gamma_O2_peak * (_df_O2 / 2.0) ** 2 / ((f_ghz - _f_O2) ** 2 + (_df_O2 / 2.0) ** 2)

    # 低频宽带氧气连续吸收（1–30 GHz 约 0.005–0.008 dB/km）
    gamma_O2_cont = 0.006 * (f_ghz / 10.0) ** 0.8
    gamma_O2 = gamma_O2 + gamma_O2_cont

    # ── 水汽比衰减 γ_H2O (dB/km) ── 22.235 GHz 单峰近似 ──
    _f_H2O = 22.235   # 水汽主吸收线 GHz
    _gamma_H2O_peak = 0.05  # 22 GHz 峰值比衰减 (dB/km)，@7.5 g/m³
    _df_H2O = 2.5    # 半峰全宽 GHz（简化）
    gamma_H2O = _gamma_H2O_peak * water_vapor_density_g_m3 / _STD_WATER_VAPOR_DENSITY
    gamma_H2O *= (_df_H2O / 2.0) ** 2 / ((f_ghz - _f_H2O) ** 2 + (_df_H2O / 2.0) ** 2)
    # 水汽宽带连续吸收
    gamma_H2O_cont = 1.5e-4 * (f_ghz ** 1.5) * (water_vapor_density_g_m3 / 7.5)
    gamma_H2O = gamma_H2O + gamma_H2O_cont

    # 总比衰减 (dB/km)
    gamma_total = gamma_O2 + gamma_H2O

    # 有效路径长度：用等效标高折算斜路径
    h_eff_km = scale_height_km
    elev_rad = math.radians(max(elevation_deg, 0.1))
    # 斜路径等效天顶方向归一化
    if elevation_deg >= 5.0:
        l_path_km = h_eff_km / math.sin(elev_rad)
    else:
        # 低仰角弦长近似
        R_e = 6371.0
        l_path_km = math.sqrt(
            2.0 * R_e * h_eff_km + h_eff_km ** 2
        ) * max(1.0 / math.sin(elev_rad), 1.0)
        l_path_km = min(l_path_km, 200.0)  # 物理上限夹紧

    a_gas = gamma_total * l_path_km
    return max(a_gas, 0.0)


def total_atmospheric_loss_db(
    freq_hz: float,
    elevation_deg: float,
    rainfall_rate_mm_h: float = 0.0,
    gs_altitude_km: float = 0.0,
    water_vapor_density_g_m3: float = _STD_WATER_VAPOR_DENSITY,
) -> dict:
    """计算总大气衰减（雨衰 + 气体吸收），返回各分量与合计。

    Parameters
    ----------
    freq_hz : float
        载波频率（Hz）。
    elevation_deg : float
        卫星仰角（度）。
    rainfall_rate_mm_h : float
        降雨率（mm/h），0 表示晴天。
    gs_altitude_km : float
        地面站海拔（km）。
    water_vapor_density_g_m3 : float
        地面水汽密度（g/m³）。

    Returns
    -------
    dict
        {
          "rain_attenuation_db": float,   # 雨衰 (dB)
          "gaseous_attenuation_db": float, # 气体吸收 (dB)
          "total_attenuation_db": float,  # 合计附加损耗 (dB)
        }
    """
    a_rain = rain_attenuation_db(
        freq_hz=freq_hz,
        elevation_deg=elevation_deg,
        rainfall_rate_mm_h=rainfall_rate_mm_h,
        gs_altitude_km=gs_altitude_km,
    )
    a_gas = gaseous_attenuation_db(
        freq_hz=freq_hz,
        elevation_deg=elevation_deg,
        water_vapor_density_g_m3=water_vapor_density_g_m3,
    )
    return {
        "rain_attenuation_db": round(a_rain, 3),
        "gaseous_attenuation_db": round(a_gas, 3),
        "total_attenuation_db": round(a_rain + a_gas, 3),
    }


# ═══════════════════════════════════════════════════════════════
#  快捷计算函数（供 orbit.py / core.py 调用）
# ═══════════════════════════════════════════════════════════════

def atmospheric_loss_for_link(
    freq_hz: float,
    elevation_deg: float,
    rainfall_rate_mm_h: float = 0.0,
    gs_altitude_km: float = 0.0,
) -> float:
    """返回合计大气衰减 (dB)，供链路预算 misc_loss_db 叠加。

    零降雨时仅包含气体吸收，非零降雨时叠加雨衰。

    Parameters
    ----------
    freq_hz : float
        载波频率（Hz）。
    elevation_deg : float
        卫星仰角（度）。
    rainfall_rate_mm_h : float
        降雨率（mm/h）。
    gs_altitude_km : float
        地面站海拔（km）。

    Returns
    -------
    float
        总大气衰减（dB），非负。
    """
    result = total_atmospheric_loss_db(
        freq_hz=freq_hz,
        elevation_deg=elevation_deg,
        rainfall_rate_mm_h=rainfall_rate_mm_h,
        gs_altitude_km=gs_altitude_km,
    )
    return result["total_attenuation_db"]
