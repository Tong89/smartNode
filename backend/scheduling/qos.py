# -*- coding: utf-8 -*-
"""QoS 与安全级感知的资源分配与准入控制。

本模块实现基于 QoS（高/中/低）和安全级别（top_secret/secret/confidential/public）
的差异化调度策略：

- 高 QoS 请求预留最低带宽保障，拥塞时保护其不被低优先级任务挤占；
- 低 QoS 请求在拥塞时主动降级（限速）或被拒绝；
- top_secret 请求仅允许经过中继/加密链路，禁止直连地面站；
- 安全约束与已有的 allowed_links 合并校验；
- 冲突时返回标准化的拒绝原因码。
"""

from __future__ import annotations

from typing import Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from backend.core import TransmissionRequest

# ==========================================
# QoS 配置常量
# ==========================================

# 高 QoS 在每个中继上预留的最低可用带宽比例
# 当已使用带宽超出 (1 - HIGH_QOS_RESERVE_RATIO)*total 时，
# 拒绝新的低 QoS 请求，保护高 QoS 任务的通路。
HIGH_QOS_RESERVE_RATIO = 0.20  # 为高 QoS 保留 20% 总带宽

# 低 QoS 请求在拥塞时允许使用的最高速率上限（Mbps）
LOW_QOS_CONGESTION_RATE_CAP = 50.0  # Mbps

# 中等 QoS 拥塞阈值：带宽占用超过此比例时开始对 medium QoS 施加限速
MEDIUM_QOS_CONGESTION_THRESHOLD = 0.75  # 75%

# 低 QoS 拥塞阈值：带宽占用超过此比例时拒绝 low QoS 请求
LOW_QOS_REJECT_THRESHOLD = 0.60  # 60%

# ==========================================
# 安全级配置常量
# ==========================================

# top_secret 仅允许中继链路（绝不走直连地面站）
TOP_SECRET_ALLOWED_LINK_TYPES = frozenset(["relay"])

# 不允许 top_secret 数据落到的地面站前缀/标签（示例：开放/公共站）
# 此处用空集，实际约束由 link_type 控制；如需扩展可填入 gs_id 子串列表
TOP_SECRET_BLOCKED_GS_IDS: frozenset = frozenset()

# ==========================================
# 标准化拒绝原因码（追加到 core.REJECTION_REASONS）
# ==========================================

QOS_REJECTION_REASONS = {
    "QOS_HIGH_BANDWIDTH_RESERVED": "高QoS带宽预留：中继可用容量不足，拒绝低QoS请求",
    "QOS_LOW_CONGESTION_REJECTED": "网络拥塞：低QoS请求在当前负载下被拒绝",
    "SECURITY_TOP_SECRET_NO_DIRECT": "安全约束：绝密数据不允许直连地面站，需经加密中继链路",
    "SECURITY_LINK_CONSTRAINT_VIOLATED": "安全约束：请求所要求的安全级别与可用链路不兼容",
}


# ==========================================
# QosAdmissionController
# ==========================================

class QosAdmissionController:
    """QoS 与安全级准入控制器。

    在调度器选链之前对请求进行预筛，决定是否允许进入调度流程，
    并可在链路候选集中移除不符合安全约束的链路类型。

    Args:
        engine: SimulationEngine 实例引用（用于读取带宽统计与中继列表）。
    """

    def __init__(self, engine) -> None:
        self.engine = engine

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def check_admission(self, req: "TransmissionRequest") -> Tuple[bool, Optional[str]]:
        """准入检查入口。

        Returns:
            (True, None)  — 允许调度；
            (False, reason_str) — 拒绝，并附带标准化原因字符串。
        """
        qos = getattr(req, "qos", None)
        security = getattr(req, "security", None)

        # 1. 安全级约束检查（优先于 QoS）
        sec_ok, sec_reason = self._check_security(req, security)
        if not sec_ok:
            return False, sec_reason

        # 2. QoS 带宽保障检查
        qos_ok, qos_reason = self._check_qos_bandwidth(req, qos)
        if not qos_ok:
            return False, qos_reason

        return True, None

    def filter_allowed_link_types(self, req: "TransmissionRequest", allowed_links: list) -> list:
        """根据安全级别过滤允许的链路类型列表。

        例如 top_secret 请求移除 "direct" 选项，仅保留 "relay"。

        Args:
            req: 传输请求对象。
            allowed_links: 原始 allowed_links 列表（来自 DATA_TYPES 配置）。

        Returns:
            过滤后的链路类型列表（可能为空，调度层需处理空列表）。
        """
        security = getattr(req, "security", None)
        if security == "top_secret":
            return [lt for lt in allowed_links if lt in TOP_SECRET_ALLOWED_LINK_TYPES]
        return list(allowed_links)

    def apply_qos_rate_cap(self, req: "TransmissionRequest", candidate_rate: float) -> float:
        """对低 QoS 请求在拥塞时施加速率上限。

        高/中 QoS 或非拥塞状态下返回原始速率，低 QoS 在拥塞时截断到
        LOW_QOS_CONGESTION_RATE_CAP。

        Args:
            req: 传输请求。
            candidate_rate: 链路计算所得速率（Mbps）。

        Returns:
            实际允许的传输速率（Mbps）。
        """
        qos = getattr(req, "qos", None)
        if qos != "low":
            return candidate_rate

        avg_util = self._avg_relay_utilization()
        if avg_util >= LOW_QOS_REJECT_THRESHOLD:
            return min(candidate_rate, LOW_QOS_CONGESTION_RATE_CAP)
        return candidate_rate

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    def _check_security(self, req: "TransmissionRequest", security: Optional[str]) -> Tuple[bool, Optional[str]]:
        """安全级约束校验。"""
        if security != "top_secret":
            return True, None

        # top_secret 的 allowed_links 必须包含 "relay"
        from backend.core import DATA_TYPES
        data_config = DATA_TYPES.get(req.data_type, {})
        original_allowed = data_config.get("allowed_links", ["direct"])
        filtered = self.filter_allowed_link_types(req, original_allowed)
        if not filtered:
            return False, QOS_REJECTION_REASONS["SECURITY_LINK_CONSTRAINT_VIOLATED"]
        return True, None

    def _check_qos_bandwidth(self, req: "TransmissionRequest", qos: Optional[str]) -> Tuple[bool, Optional[str]]:
        """QoS 带宽保障校验。

        - low QoS：拥塞（>= LOW_QOS_REJECT_THRESHOLD）时拒绝；
        - medium QoS：不拒绝，但会在速率层面限速（由 apply_qos_rate_cap 负责）；
        - high QoS：始终允许（受益方）。
        """
        if qos == "high" or qos is None:
            return True, None

        avg_util = self._avg_relay_utilization()

        if qos == "low" and avg_util >= LOW_QOS_REJECT_THRESHOLD:
            return False, QOS_REJECTION_REASONS["QOS_LOW_CONGESTION_REJECTED"]

        # 当有 high QoS 请求竞争时，保护预留带宽
        if qos == "low" and self._high_qos_reserve_violated():
            return False, QOS_REJECTION_REASONS["QOS_HIGH_BANDWIDTH_RESERVED"]

        return True, None

    def _avg_relay_utilization(self) -> float:
        """计算所有 GEO 中继的平均带宽利用率（0.0 ~ 1.0）。"""
        eng = self.engine
        geo_relays = eng.geo_relays
        if not geo_relays:
            return 0.0

        relay_bw_usage = eng.stats.get("relay_bandwidth_usage", {})
        total_util = 0.0
        for geo in geo_relays:
            relay_id = geo["id"]
            relay_bw = geo.get("bandwidth", 2000)
            used = relay_bw_usage.get(relay_id, 0)
            total_util += min(1.0, used / relay_bw) if relay_bw > 0 else 0.0
        return total_util / len(geo_relays)

    def _high_qos_reserve_violated(self) -> bool:
        """当有高 QoS 请求在队列中时，检查预留带宽是否已被占满。

        若任意中继的可用带宽低于 HIGH_QOS_RESERVE_RATIO * total，
        则判定预留被侵占，拒绝低 QoS 请求进入。
        """
        eng = self.engine

        # 只有存在高 QoS 活跃/等待请求时才启用保护
        has_high_qos = any(
            getattr(r, "qos", None) == "high" and r.status in ("accepted", "transmitting")
            for r in eng.transmission_requests
        )
        if not has_high_qos:
            return False

        relay_bw_usage = eng.stats.get("relay_bandwidth_usage", {})
        for geo in eng.geo_relays:
            relay_id = geo["id"]
            relay_bw = geo.get("bandwidth", 2000)
            used = relay_bw_usage.get(relay_id, 0)
            available_ratio = (relay_bw - used) / relay_bw if relay_bw > 0 else 0.0
            if available_ratio < HIGH_QOS_RESERVE_RATIO:
                return True  # 至少一个��继的保留带宽被侵占
        return False


# ==========================================
# QoS 感知的 GreedyMaxRateStrategy 扩展
# ==========================================

class QosAwareStrategy:
    """在 GreedyMaxRateStrategy 基础上叠加 QoS 与安全级约束。

    作为装饰器包裹底层策略，在候选链路集合上施加安全过滤，
    并对低 QoS 请求应用速率上限。
    """

    name = "qos_aware"

    def __init__(self, base_strategy=None) -> None:
        if base_strategy is None:
            from backend.scheduling.strategy import GreedyMaxRateStrategy
            base_strategy = GreedyMaxRateStrategy()
        self.base_strategy = base_strategy

    def select(self, scheduler, req, satellite, sat_pos):
        """选链入口：先过滤安全不兼容链路，再委托基础策略，最后限速。"""
        from backend.core import DATA_TYPES

        qos_ctrl = QosAdmissionController(scheduler.engine)
        security = getattr(req, "security", None)
        qos = getattr(req, "qos", None)

        data_config = DATA_TYPES.get(req.data_type, {})
        original_allowed = data_config.get("allowed_links", ["direct"])

        # 安全级链路过滤
        filtered_allowed = qos_ctrl.filter_allowed_link_types(req, original_allowed)

        if not filtered_allowed:
            # 无可用链路类型（安全约束导致）
            return None

        # 若安全约束收窄了链路集合，临时替换 req 的可用链路字段
        # （通过猴子补丁传入 base_strategy，避免修改 DATA_TYPES 全局状态）
        _original_data_types_entry = data_config.copy()
        if set(filtered_allowed) != set(original_allowed):
            # 在调用 base_strategy.select 前，临时覆盖 allowed_links
            _patched_data_types = dict(DATA_TYPES)
            _patched_entry = dict(_original_data_types_entry)
            _patched_entry["allowed_links"] = filtered_allowed
            _patched_data_types[req.data_type] = _patched_entry

            # 用局部补丁调用底层策略
            link = self._select_with_patched_types(
                scheduler, req, satellite, sat_pos, _patched_data_types, filtered_allowed
            )
        else:
            link = self.base_strategy.select(scheduler, req, satellite, sat_pos)

        if link is None:
            return None

        # 低 QoS 速率上限
        if qos == "low":
            original_rate = link["rate"]
            capped_rate = qos_ctrl.apply_qos_rate_cap(req, original_rate)
            if capped_rate != original_rate:
                link = dict(link)
                link["rate"] = capped_rate

        return link

    def _select_with_patched_types(self, scheduler, req, satellite, sat_pos,
                                   patched_data_types, filtered_allowed):
        """使用经安全约束过滤后的 allowed_links 执行贪心选链。

        仅复用 GreedyMaxRateStrategy 内部逻辑，避免修改全局 DATA_TYPES。
        """
        from backend.scheduling.strategy import GreedyMaxRateStrategy

        eng = scheduler.engine
        is_immediate_type = req.data_type in ["TASK_CMD", "INTEL"]
        best_link = None
        best_rate = 0.0

        def can_use_satellite():
            return is_immediate_type or not scheduler.resource_busy_by_other(
                "satellites", satellite.sat_id, req.id
            )

        def can_use_ground_station(gs_id):
            return is_immediate_type or not scheduler.resource_busy_by_other(
                "ground_stations", gs_id, req.id
            )

        if "direct" in filtered_allowed and can_use_satellite():
            for gs in scheduler.ground_station_candidates(req):
                if can_use_ground_station(gs["id"]) and eng.check_visibility(sat_pos, gs, min_elevation=10):
                    rate = eng._calculate_direct_rate(sat_pos, gs, req.data_type)
                    if rate > best_rate:
                        best_rate = rate
                        best_link = {
                            "method": "direct",
                            "ground_station": gs["id"],
                            "relay": None,
                            "relay2": None,
                            "rate": rate,
                        }

        if "relay" in filtered_allowed and can_use_satellite():
            for geo in eng.geo_relays:
                geo_pos = eng.get_geo_position(geo)
                if not eng.check_geo_visibility(sat_pos, geo_pos):
                    continue
                for gs in scheduler.ground_station_candidates(req):
                    if not can_use_ground_station(gs["id"]):
                        continue
                    if not eng.check_visibility(geo_pos, gs, min_elevation=5):
                        continue
                    rate = eng._calculate_relay_rate(sat_pos, geo_pos, gs, req.data_type)
                    if rate > best_rate and scheduler.relay_can_carry_request(geo["id"], rate, req):
                        best_rate = rate
                        best_link = {
                            "method": "relay",
                            "ground_station": gs["id"],
                            "relay": geo["id"],
                            "relay2": None,
                            "rate": rate,
                        }

        return best_link
