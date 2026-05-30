# -*- coding: utf-8 -*-
"""通信链路计算子包。

提供链路预算（Link Budget）分析：EIRP、G/T、自由空间路径损耗、
C/N0、Eb/N0、SNR 以及 QPSK/8PSK/16APSK 的 BER 与可达速率；
附带 ITU-R P.838/P.618/P.676 大气衰减（雨衰 + 气体吸收）模型。
"""
from .link_budget import (
    LinkBudget,
    LinkBudgetResult,
    compute_fspl_db,
    compute_cn0,
    compute_ebn0,
    compute_ber,
    compute_capacity_mbps,
    link_budget_direct,
    link_budget_relay,
    link_budget_inter_satellite,
)
from .atmosphere import (
    rain_attenuation_db,
    gaseous_attenuation_db,
    total_atmospheric_loss_db,
    atmospheric_loss_for_link,
)
from .laser_isl import (
    LaserISLModel,
    LaserISLResult,
    check_los_visibility,
    laser_isl_rate,
    laser_isl_check,
)
from .beam_pointing import (
    BeamPointing,
    BeamPointingResult,
    check_scan_range,
    scan_loss_db,
    scan_loss_factor,
    rate_with_scan_loss,
    repoint_time_ms,
    from_opportunistic_station,
    from_geo_satellite,
)

__all__ = [
    "LinkBudget",
    "LinkBudgetResult",
    "compute_fspl_db",
    "compute_cn0",
    "compute_ebn0",
    "compute_ber",
    "compute_capacity_mbps",
    "link_budget_direct",
    "link_budget_relay",
    "link_budget_inter_satellite",
    # Atmospheric attenuation (ITU-R P.838/P.618/P.676)
    "rain_attenuation_db",
    "gaseous_attenuation_db",
    "total_atmospheric_loss_db",
    "atmospheric_loss_for_link",
    # Laser ISL physics model
    "LaserISLModel",
    "LaserISLResult",
    "check_los_visibility",
    "laser_isl_rate",
    "laser_isl_check",
    # Beam pointing & phased-array scan constraints
    "BeamPointing",
    "BeamPointingResult",
    "check_scan_range",
    "scan_loss_db",
    "scan_loss_factor",
    "rate_with_scan_loss",
    "repoint_time_ms",
    "from_opportunistic_station",
    "from_geo_satellite",
]
