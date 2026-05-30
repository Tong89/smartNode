# -*- coding: utf-8 -*-
"""通信链路计算子包。

提供链路预算（Link Budget）分析：EIRP、G/T、自由空间路径损耗、
C/N0、Eb/N0、SNR 以及 QPSK/8PSK/16APSK 的 BER 与可达速率。
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
]
