# -*- coding: utf-8 -*-
"""调度决策轨迹记录模块（DecisionTrace）。

为每个调度决策生成结构化解释记录，包含：
- 候选链路列表及各自的速率/能耗/评分
- 最终选中项与得分
- 被排除候选的原因
- 抢占/降级动作

轨迹存入有限长度环形缓冲，可通过 API 按 req_id 或批量查询。
"""

from __future__ import annotations

import collections
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ==========================================
# 最大缓冲条数（防止无限增长）
# ==========================================
MAX_TRACE_BUFFER = 500  # 最多保留最近 500 条决策轨迹


# ==========================================
# 数据结构
# ==========================================

@dataclass
class CandidateLink:
    """候选链路及其评分信息。"""
    method: str                        # "direct" | "relay" | "multi_relay"
    ground_station: Optional[str]      # 地面站 ID
    relay: Optional[str]               # 第一跳 GEO 中继 ID
    relay2: Optional[str]              # 第二跳 GEO 中继 ID（双跳时使用）
    rate_mbps: float                   # 预估速率（Mbps）
    score: float                       # 综合评分（0.0 ~ 1.0+，越高越优）
    excluded: bool = False             # 是否被排除（未入选）
    exclude_reason: Optional[str] = None  # 排除原因（如"带宽不足"、"遮蔽"等）

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DecisionTrace:
    """单次调度决策的完整轨迹记录。"""
    req_id: str                         # 请求 ID（如 "REQ_0001"）
    satellite_id: str                   # 执行调度的卫星 ID
    sim_time: float                     # 调度时刻（仿真时间，秒）
    real_time: float                    # 调度时刻（真实 Unix 时间戳）
    outcome: str                        # "scheduled" | "rejected" | "rerouted"

    candidates: List[CandidateLink] = field(default_factory=list)
    selected: Optional[CandidateLink] = None   # 最终选中的候选链路
    reject_reason: Optional[str] = None        # 拒绝/无链路原因

    # 辅助决策信息
    data_type: Optional[str] = None
    qos: Optional[str] = None
    security: Optional[str] = None
    priority: int = 0

    # 抢占/降级记录
    preemption_action: Optional[str] = None    # 如 "preempted_low_qos_request"
    demotion_action: Optional[str] = None      # 如 "rate_capped_to_50mbps"

    def to_dict(self) -> dict:
        d = {
            "req_id": self.req_id,
            "satellite_id": self.satellite_id,
            "sim_time": self.sim_time,
            "real_time": self.real_time,
            "outcome": self.outcome,
            "data_type": self.data_type,
            "qos": self.qos,
            "security": self.security,
            "priority": self.priority,
            "candidates": [c.to_dict() for c in self.candidates],
            "selected": self.selected.to_dict() if self.selected else None,
            "reject_reason": self.reject_reason,
            "preemption_action": self.preemption_action,
            "demotion_action": self.demotion_action,
        }
        return d


# ==========================================
# 环形缓冲（DecisionTraceBuffer）
# ==========================================

class DecisionTraceBuffer:
    """固定容量的调度决策轨迹环形缓冲。

    内部使用 deque(maxlen) 保证不超过 MAX_TRACE_BUFFER 条记录，
    同时维护 req_id -> trace 的索引字典以支持 O(1) 查询。
    当缓冲满时，最旧的记录及其索引条目会被自动淘汰。
    """

    def __init__(self, maxlen: int = MAX_TRACE_BUFFER) -> None:
        self._maxlen = maxlen
        self._buffer: collections.deque = collections.deque(maxlen=maxlen)
        self._index: Dict[str, DecisionTrace] = {}

    def add(self, trace: DecisionTrace) -> None:
        """追加一条决策轨迹；若缓冲满则淘汰最旧条目。"""
        if len(self._buffer) >= self._maxlen:
            # 淘汰最旧条目，从索引中移除
            oldest = self._buffer[0]
            self._index.pop(oldest.req_id, None)
        self._buffer.append(trace)
        self._index[trace.req_id] = trace

    def get(self, req_id: str) -> Optional[DecisionTrace]:
        """按 req_id 查询决策轨迹，不存在时返回 None。"""
        return self._index.get(req_id)

    def list_all(self) -> List[DecisionTrace]:
        """返回缓冲中所有轨迹（从旧到新）。"""
        return list(self._buffer)

    def __len__(self) -> int:
        return len(self._buffer)

    @property
    def maxlen(self) -> int:
        return self._maxlen


# ==========================================
# 辅助：构建 DecisionTrace
# ==========================================

def build_trace_from_link_selection(
    req,
    satellite_id: str,
    sim_time: float,
    all_candidates: List[Dict[str, Any]],
    selected_link: Optional[Dict[str, Any]],
    outcome: str,
    reject_reason: Optional[str] = None,
    preemption_action: Optional[str] = None,
    demotion_action: Optional[str] = None,
) -> DecisionTrace:
    """根据调度结果构建 DecisionTrace 实例。

    Args:
        req: TransmissionRequest 实例。
        satellite_id: 当前卫星 ID。
        sim_time: 仿真时间（秒）。
        all_candidates: 所有被评估的候选链路列表，每项为 dict：
            {method, ground_station, relay, relay2, rate, score,
             excluded, exclude_reason}
        selected_link: 最终选中的链路 dict（未选中时为 None）。
        outcome: "scheduled" | "rejected" | "rerouted"
        reject_reason: 拒绝原因字符串（outcome="rejected" 时填写）。
        preemption_action: 抢占动作描述。
        demotion_action: 降级动作描述（如速率截断）。

    Returns:
        构建好的 DecisionTrace 实例。
    """
    candidates = []
    selected_candidate: Optional[CandidateLink] = None

    for c in all_candidates:
        cl = CandidateLink(
            method=c.get("method", ""),
            ground_station=c.get("ground_station"),
            relay=c.get("relay"),
            relay2=c.get("relay2"),
            rate_mbps=float(c.get("rate", 0.0)),
            score=float(c.get("score", c.get("rate", 0.0))),
            excluded=bool(c.get("excluded", False)),
            exclude_reason=c.get("exclude_reason"),
        )
        candidates.append(cl)

    # 构建选中候选对象
    if selected_link is not None:
        selected_candidate = CandidateLink(
            method=selected_link.get("method", ""),
            ground_station=selected_link.get("ground_station"),
            relay=selected_link.get("relay"),
            relay2=selected_link.get("relay2"),
            rate_mbps=float(selected_link.get("rate", 0.0)),
            score=float(selected_link.get("score", selected_link.get("rate", 0.0))),
            excluded=False,
        )

    trace = DecisionTrace(
        req_id=req.id,
        satellite_id=satellite_id,
        sim_time=sim_time,
        real_time=time.time(),
        outcome=outcome,
        candidates=candidates,
        selected=selected_candidate,
        reject_reason=reject_reason,
        data_type=getattr(req, "data_type", None),
        qos=getattr(req, "qos", None),
        security=getattr(req, "security", None),
        priority=getattr(req, "priority", 0),
        preemption_action=preemption_action,
        demotion_action=demotion_action,
    )
    return trace
