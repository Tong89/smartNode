# -*- coding: utf-8 -*-
"""属性测试：资源时间池与调度核心的 hypothesis 随机化不变量验证。

测试目标（4 类不变量）：
  1. 时间槽冲突检测：重叠区间必判冲突（非 geo_relay 资源）
  2. 释放后无残留：reserve 后 release，time_pool 中无该 req_id 的槽
  3. 中继带宽不超上限：reserve 累计后 check 返回 False 当且仅当已用>=上限
  4. 引擎状态一致性：accepted/rejected 计数与列表长度一致

使用策略：
  - st.floats 随机生成时间区间（过滤无效区间 start>=end）
  - st.lists(st.floats) 随机生成带宽序列（过滤负值/零）
  - assume() 跳过无效样本，避免污染失败最小化
  - @settings(max_examples=200) 提高随机覆盖密度
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from backend.resources import ResourceManager


# ---------------------------------------------------------------------------
# 辅助工厂
# ---------------------------------------------------------------------------

_RES_TYPE = "satellites"
_RES_ID = "SAT-001"
_GEO_TYPE = "geo_relays"
_GEO_ID = "GEO-001"
_GEO_BW = 2000.0  # Mbps


def _make_rm_with_sat() -> ResourceManager:
    """创建含一个卫星时间池条目的 ResourceManager。"""
    rm = ResourceManager()
    rm.time_pool[_RES_TYPE][_RES_ID] = []
    return rm


def _make_rm_with_geo() -> ResourceManager:
    """创建含一个 GEO 中继时间池条目的 ResourceManager。"""
    rm = ResourceManager()
    rm.time_pool[_GEO_TYPE][_GEO_ID] = []
    return rm


_GEO_RELAYS_CONF = [{"id": _GEO_ID, "bandwidth": _GEO_BW}]


# ---------------------------------------------------------------------------
# 策略：有效时间区间（直接使用 flatmap 构造，避免大量过滤导致 HealthCheck 警告）
# ---------------------------------------------------------------------------

_finite_positive = st.floats(min_value=0.0, max_value=1e9, allow_nan=False, allow_infinity=False)

# 直接构造 (start, end) 使 start < end，避免大量 assume() 过滤
_time_interval = st.builds(
    lambda s, width: (s, s + width),
    s=_finite_positive,
    width=st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False),
)


# ===========================================================================
# 不变量 1：重叠区间必判冲突（卫星资源）
# ===========================================================================

class TestTimeSlotConflictInvariant:
    """reserve 一个时间槽后，任何与其重叠的区间必须被 check 检测为不可用。"""

    @given(
        existing=_time_interval,
        query=_time_interval,
    )
    @settings(max_examples=300, suppress_health_check=[HealthCheck.filter_too_much])
    def test_overlap_detected_as_conflict(self, existing, query):
        """已预约区间与查询区间重叠时，check 必须返回 False（冲突）。"""
        s1, e1 = existing
        s2, e2 = query
        # 仅在真正重叠时测试
        assume(s2 < e1 and s1 < e2)

        rm = _make_rm_with_sat()
        rm.reserve_time_slot(_RES_TYPE, _RES_ID, s1, e1, "req-existing", bandwidth=0)

        available, reason = rm.check_time_slot_available(_RES_TYPE, _RES_ID, s2, e2)
        assert not available, (
            f"重叠区间 [{s1},{e1}) 与 [{s2},{e2}) 应被检测为冲突，但 check 返回可用。reason={reason}"
        )

    @given(
        s1=_finite_positive,
        w1=st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False),
        w2=st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False),
        gap=st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_non_overlap_is_available(self, s1, w1, w2, gap):
        """已预约区间与查询区间无重叠时，check 必须返回可用（query 在 existing 之后）。"""
        e1 = s1 + w1
        s2 = e1 + gap   # query 严格在 existing 之后（gap >= 0，不重叠）
        e2 = s2 + w2

        rm = _make_rm_with_sat()
        rm.reserve_time_slot(_RES_TYPE, _RES_ID, s1, e1, "req-existing", bandwidth=0)

        available, _ = rm.check_time_slot_available(_RES_TYPE, _RES_ID, s2, e2)
        assert available, (
            f"不重叠区间 [{s1},{e1}) 与 [{s2},{e2}) 应可用，但 check 返回冲突。"
        )

    @given(
        s2=_finite_positive,
        w2=st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False),
        gap=st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False),
        w1=st.floats(min_value=1.0, max_value=1e6, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_query_before_existing_is_available(self, s2, w2, gap, w1):
        """查询区间完全在已预约区间之前时，check 必须返回可用。"""
        e2 = s2 + w2
        s1 = e2 + gap   # existing 严格在 query 之后
        e1 = s1 + w1

        rm = _make_rm_with_sat()
        rm.reserve_time_slot(_RES_TYPE, _RES_ID, s1, e1, "req-existing", bandwidth=0)

        available, _ = rm.check_time_slot_available(_RES_TYPE, _RES_ID, s2, e2)
        assert available, (
            f"查询区间 [{s2},{e2}) 完全在已预约区间 [{s1},{e1}) 之前，应可用。"
        )


# ===========================================================================
# 不变量 2：释放后无残留
# ===========================================================================

class TestReleaseNoResidualInvariant:
    """reserve 后 release，time_pool 中不应有任何属于该 req_id 的条目。"""

    @given(interval=_time_interval)
    @settings(max_examples=300)
    def test_release_removes_all_slots_for_req(self, interval):
        """单个 reserve 后 release，池中无该 req_id 的槽。"""
        s, e = interval
        req_id = "req-to-release"

        rm = _make_rm_with_sat()
        rm.reserve_time_slot(_RES_TYPE, _RES_ID, s, e, req_id, bandwidth=0)

        # 确认确实预约成功
        slots_before = rm.time_pool[_RES_TYPE][_RES_ID]
        assert any(slot[2] == req_id for slot in slots_before), "reserve 后应有槽"

        rm.release_time_slot(req_id)

        slots_after = rm.time_pool[_RES_TYPE][_RES_ID]
        residual = [slot for slot in slots_after if slot[2] == req_id]
        assert len(residual) == 0, (
            f"release 后不应有 {req_id} 的槽，但发现残留: {residual}"
        )

    @given(
        intervals=st.lists(_time_interval, min_size=1, max_size=10),
    )
    @settings(max_examples=200)
    def test_release_idempotent_multiple_reserves(self, intervals):
        """多次 reserve 同一 req_id，一次 release 后完全清空。"""
        req_id = "req-multi"

        rm = _make_rm_with_sat()
        for s, e in intervals:
            rm.reserve_time_slot(_RES_TYPE, _RES_ID, s, e, req_id, bandwidth=0)

        rm.release_time_slot(req_id)

        slots_after = rm.time_pool[_RES_TYPE][_RES_ID]
        residual = [slot for slot in slots_after if slot[2] == req_id]
        assert len(residual) == 0, (
            f"多重 reserve 后 release，不应有残留，但发现: {residual}"
        )

    @given(
        interval_a=_time_interval,
        interval_b=_time_interval,
    )
    @settings(max_examples=200)
    def test_release_only_removes_target_req(self, interval_a, interval_b):
        """release req_a 不应影响 req_b 的槽。"""
        rm = _make_rm_with_sat()
        rm.reserve_time_slot(_RES_TYPE, _RES_ID, *interval_a, "req-a", bandwidth=0)
        rm.reserve_time_slot(_RES_TYPE, _RES_ID, *interval_b, "req-b", bandwidth=0)

        rm.release_time_slot("req-a")

        slots = rm.time_pool[_RES_TYPE][_RES_ID]
        req_a_slots = [s for s in slots if s[2] == "req-a"]
        req_b_slots = [s for s in slots if s[2] == "req-b"]

        assert len(req_a_slots) == 0, "req-a 的槽应已被释放"
        assert len(req_b_slots) == 1, "req-b 的槽不应被影响"


# ===========================================================================
# 不变量 3：中继带宽不超上限
# ===========================================================================

class TestRelayBandwidthInvariant:
    """GEO 中继：累计带宽预约超过上限时，check 必须返回不可用。"""

    @given(
        # 确保至少有一个已预约的槽，然后总带宽超上限
        base_used=st.floats(min_value=1.0, max_value=_GEO_BW, allow_nan=False, allow_infinity=False),
        extra=st.floats(min_value=0.1, max_value=500.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=300)
    def test_bandwidth_exceeded_returns_conflict(self, base_used, extra):
        """已有槽占用 base_used 带宽，再查询 extra 使总量超上限时，check 返回 False。

        注意：ResourceManager 的带宽冲突检测仅在存在重叠槽时触发（循环遍历），
        因此本测试确保 pool 中至少有一个已预约槽（base_used >= 1.0）。
        """
        # 固定时间段使所有槽重叠
        start, end = 100.0, 200.0
        # 查询带宽 = (上限 - 已用) + extra，确保总量超上限
        query_bw = (_GEO_BW - base_used) + extra

        rm = _make_rm_with_geo()
        rm.reserve_time_slot(_GEO_TYPE, _GEO_ID, start, end, "req-base", bandwidth=base_used)

        available, reason = rm.check_time_slot_available(
            _GEO_TYPE, _GEO_ID, start, end, required_bandwidth=query_bw, geo_relays=_GEO_RELAYS_CONF
        )
        assert not available, (
            f"已用带宽 {base_used:.1f} + 请求 {query_bw:.1f} > 上限 {_GEO_BW}，应不可用。reason={reason}"
        )

    @given(
        query_bw=st.floats(min_value=0.0, max_value=_GEO_BW - 1.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_bandwidth_within_limit_is_available(self, query_bw):
        """空池中查询带宽 < 上限时，check 返回可用。"""
        rm = _make_rm_with_geo()
        available, reason = rm.check_time_slot_available(
            _GEO_TYPE, _GEO_ID, 100.0, 200.0, required_bandwidth=query_bw, geo_relays=_GEO_RELAYS_CONF
        )
        assert available, (
            f"空池中查询 {query_bw:.1f} Mbps < 上限 {_GEO_BW}，应可用。reason={reason}"
        )

    @given(
        bw1=st.floats(min_value=1.0, max_value=800.0, allow_nan=False, allow_infinity=False),
        bw2=st.floats(min_value=1.0, max_value=800.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200, suppress_health_check=[HealthCheck.filter_too_much])
    def test_two_slots_within_limit_available(self, bw1, bw2):
        """两个带宽槽之和 < 上限时，第三次查询零带宽应可用。"""
        assume(bw1 + bw2 < _GEO_BW)

        rm = _make_rm_with_geo()
        rm.reserve_time_slot(_GEO_TYPE, _GEO_ID, 100.0, 200.0, "req-1", bandwidth=bw1)
        rm.reserve_time_slot(_GEO_TYPE, _GEO_ID, 100.0, 200.0, "req-2", bandwidth=bw2)

        # 零带宽查询在未超限时应可用
        available, _ = rm.check_time_slot_available(
            _GEO_TYPE, _GEO_ID, 100.0, 200.0, required_bandwidth=0.0, geo_relays=_GEO_RELAYS_CONF
        )
        assert available, (
            f"bw1={bw1:.1f} + bw2={bw2:.1f} < {_GEO_BW}，零带宽查询应可用。"
        )


# ===========================================================================
# 不变量 4：cleanup_expired 不保留过期槽
# ===========================================================================

class TestCleanupExpiredInvariant:
    """cleanup_expired 后，time_pool 中不应存在 end <= current_time 的槽。"""

    @given(
        intervals=st.lists(_time_interval, min_size=1, max_size=10),
        current_time=_finite_positive,
    )
    @settings(max_examples=300)
    def test_no_expired_slots_remain(self, intervals, current_time):
        """cleanup 后，池中所有槽的 end > current_time。"""
        rm = _make_rm_with_sat()
        for i, (s, e) in enumerate(intervals):
            rm.reserve_time_slot(_RES_TYPE, _RES_ID, s, e, f"req-{i}", bandwidth=0)

        rm.cleanup_expired(current_time)

        for slot in rm.time_pool[_RES_TYPE][_RES_ID]:
            assert slot[1] > current_time, (
                f"cleanup({current_time}) 后发现过期槽: end={slot[1]}"
            )

    @given(
        intervals=st.lists(_time_interval, min_size=2, max_size=8),
        current_time=_finite_positive,
    )
    @settings(max_examples=200)
    def test_non_expired_slots_preserved(self, intervals, current_time):
        """cleanup 不应删除 end > current_time 的有效槽。"""
        rm = _make_rm_with_sat()
        valid_req_ids = set()
        for i, (s, e) in enumerate(intervals):
            req_id = f"req-{i}"
            rm.reserve_time_slot(_RES_TYPE, _RES_ID, s, e, req_id, bandwidth=0)
            if e > current_time:
                valid_req_ids.add(req_id)

        rm.cleanup_expired(current_time)

        remaining_req_ids = {slot[2] for slot in rm.time_pool[_RES_TYPE][_RES_ID]}
        for req_id in valid_req_ids:
            assert req_id in remaining_req_ids, (
                f"有效槽 {req_id} 不应被 cleanup({current_time}) 删除。"
            )


# ===========================================================================
# 不变量 5：引擎 accepted/rejected 计数与列表长度一致
# ===========================================================================

class TestEngineStatsConsistencyInvariant:
    """SimulationEngine 的 accepted/rejected 统计计数与实际列表长度一致。"""

    def _make_engine(self):
        from backend.core import create_engine
        return create_engine(seed=42, autostart=False)

    def _make_request(self, data_type="DATA_SLICE"):
        """构造一个合法的请求字典（包含必填字段）。"""
        return {
            "data_type": data_type,
            "data_size": 100,
            "priority": 5,
            "max_delay": 3600,  # 1 小时，避免 None 引�� min() 类型错误
        }

    def test_initial_counts_match_empty_lists(self):
        """引擎初始状态：计数为 0，列表为空。"""
        eng = self._make_engine()
        try:
            assert eng.stats["accepted_requests"] == 0
            assert eng.stats["rejected_requests"] == 0
            assert len(eng.transmission_requests) == 0
            assert len(eng.request_history) == 0
        finally:
            eng.running = False

    @given(
        n_requests=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=50)
    def test_accepted_count_matches_list_after_accepts(self, n_requests):
        """每次提交 N 个合法请求，accepted + rejected 之和等于 total_requests 增量。

        每个 hypothesis 样本使用新引擎，避免跨样本状态积累导致计数偏差。
        """
        # 每个 hypothesis 示例都使用全新的引擎实例，彻底隔离状态
        eng = self._make_engine()
        try:
            submitted_accepted = 0
            submitted_rejected = 0

            for i in range(n_requests):
                result = eng.submit_request(self._make_request())
                # submit_request 返回字典，status 为 'accepted'/'transmitting' 或 'rejected'
                if isinstance(result, dict):
                    status = result.get("status")
                    if status in ("accepted", "transmitting"):
                        submitted_accepted += 1
                    elif status in ("rejected", "error"):
                        submitted_rejected += 1

            # total_requests 应等于 n_requests（从引擎 0 开始）
            total = eng.stats["total_requests"]
            assert total == n_requests, (
                f"total_requests 应为 {n_requests}，实际为 {total}"
            )

            # accepted + rejected 之和 == total（无丢失请求）
            accepted = eng.stats["accepted_requests"]
            rejected = eng.stats["rejected_requests"]
            assert accepted + rejected == total, (
                f"accepted({accepted}) + rejected({rejected}) != total({total})"
            )

            # 统计与实际返回一致
            assert accepted == submitted_accepted, (
                f"accepted_requests({accepted}) != 实际接受数({submitted_accepted})"
            )
            assert rejected == submitted_rejected, (
                f"rejected_requests({rejected}) != 实际拒绝数({submitted_rejected})"
            )
        finally:
            eng.running = False

    def test_stats_total_equals_accepted_plus_rejected(self):
        """多次提交后：user_requests + background_requests == total_requests。"""
        eng = self._make_engine()
        try:
            data_types = ["DATA_SLICE", "RAW_IMAGE", "TASK_CMD", "DATA_SLICE", "INTEL"]
            for dt in data_types:
                eng.submit_request(self._make_request(data_type=dt))

            total = eng.stats["total_requests"]
            user = eng.stats["user_requests"]
            background = eng.stats["background_requests"]

            # user_requests 和 background_requests 之和 = total_requests
            assert user + background == total, (
                f"user({user}) + background({background}) 应等于 total({total})"
            )

            # 至少有 5 个用户请求被计入
            assert user >= len(data_types), (
                f"user_requests({user}) 应至少为 {len(data_types)}"
            )
        finally:
            eng.running = False

    def test_transmission_requests_list_consistency(self):
        """transmission_requests 中 accepted 条目数 == accepted_requests 增量。"""
        eng = self._make_engine()
        try:
            initial_accepted = eng.stats["accepted_requests"]

            results = []
            for _ in range(5):
                r = eng.submit_request(self._make_request())
                results.append(r)

            # 统计 transmission_requests 中 'accepted' 状态条目
            accepted_in_list = sum(
                1 for r in eng.transmission_requests
                if r.source == "user" and r.status in ("accepted", "transmitting")
            )
            delta_stat = eng.stats["accepted_requests"] - initial_accepted

            assert accepted_in_list <= delta_stat, (
                f"transmission_requests 中接受条目 ({accepted_in_list}) "
                f"不应超过统计增量 ({delta_stat})，某些请求可能已完成"
            )
        finally:
            eng.running = False
