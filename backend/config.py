# -*- coding: utf-8 -*-
"""集中管理仿真魔法数与常量。

将散落在 core.py / api.py 的速率基准、带宽上限、调度阈值等以具名常量收敛于此，
便于统一调参与测试。数值与抽取前保持一致。
"""

# 仿真时钟
TIME_SCALE = 10  # 仿真加速倍率

# 资源带宽上限 (Mbps)
SATELLITE_MAX_BANDWIDTH = 600
GS_MAX_BANDWIDTH = 1000
DEFAULT_RELAY_BANDWIDTH = 2000

# 调度与切换阈值
RESOURCE_TIGHT_THRESHOLD = 0.95   # 平均利用率超过此值视为资源紧张
HANDOVER_RATE_RATIO = 1.2         # 链路切换：新速率需高于当前速率的倍数
HANDOVER_MIN_ELEVATION = 15       # 切换判定的最小仰角（防抖）

# 基础链路速率 (Mbps)
DIRECT_RATE_KA = 200
DIRECT_RATE_X = 100
RELAY_RATE_LEO_GEO = 500
RELAY_RATE_GEO_GS = 400
