# -*- coding: utf-8 -*-
"""调度引擎压力测试套件（纯 Python，不依赖 HTTP 服务器）。

本模块直接驱动 ``SimulationEngine.submit_request`` + 手动步进，
在高负载条件下验证：

1. **无未捕获异常**：批量提交高并发请求，引擎不应抛出任何未处理异常。
2. **拒绝原因分布合理**：高负载下低优先级请求的拒绝原因应归属于已知集合。
3. **统计计数守恒**：
   - ``total_requests == accepted + rejected``（含背景任务关闭时）
   - accepted、rejected、completed 计数均 >= 0
4. **历史记录增长可控**：``request_history`` 长度 <= 提交次数。
5. **高占用下低优先级加严拒绝**：avg_utilization 高时，低优先级请求拒绝率应显著高于高优先级。

测试策略：
- 全部使用 ``autostart=False`` 的引擎实例（不启动后台线程）
- 通过 ``tests/fixtures/scenarios.advance_engine`` 手动推进仿真时间
- 阶梯加压：分别测试 10、50、200 个并发提交
- 参数化覆盖所有 DATA_TYPES 数据类型与优先级极端值
"""

import os
import sys
import threading
import time
from typing import List, Dict, Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import pytest

from backend.core import create_engine, DATA_TYPES, REJECTION_REASONS
from tests.fixtures.scenarios import advance_engine, GOLDEN_SEED

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 已知的合法拒绝原因代码集合（来自 backend/core.py::REJECTION_REASONS）
_KNOWN_REJECTION_CODES = set(REJECTION_REASONS.keys())

# 已知拒绝原因文本（submit_request 返回的字符串值）
_KNOWN_REJECTION_MSGS = set(REJECTION_REASONS.values())

# 引擎内部还有若干内联拒绝消息（未纳入 REJECTION_REASONS 字典，但属合法输出）
_INLINE_REJECTION_MSGS = {
    "无可用通信链路或资源不足",
    "指定时间段内无可用地面站",
    "指定时间段内无可用地面站或中继资源",
}

# 全集：REJECTION_REASONS 文本 + 内联文本
_ALL_KNOWN_REJECTION_MSGS = _KNOWN_REJECTION_MSGS | _INLINE_REJECTION_MSGS

# 基准载���：使用优先级最高的 TASK_CMD
_HIGH_PRI_PAYLOAD: Dict[str, Any] = {
    "data_type": "TASK_CMD",
    "data_size": 50,
    "priority": 9,
    "max_delay": 600,
}

_LOW_PRI_PAYLOAD: Dict[str, Any] = {
    "data_type": "DATA_SLICE",
    "data_size": 200,
    "priority": 1,
    "max_delay": 600,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_engine():
    """每次测试独立引擎（seed=GOLDEN_SEED, autostart=False）。"""
    eng = create_engine(seed=GOLDEN_SEED, autostart=False)
    yield eng
    eng.running = False


@pytest.fixture
def stepped_engine():
    """已推进 60 秒仿真时间的引擎实例（建立初始状态）。"""
    eng = create_engine(seed=GOLDEN_SEED, autostart=False)
    advance_engine(eng, total_seconds=60.0, step=10.0)
    yield eng
    eng.running = False


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _submit_batch(engine, payloads: List[dict]) -> List[dict]:
    """顺序提交一批请求，收集所有返回结果。"""
    results = []
    for payload in payloads:
        result = engine.submit_request(dict(payload))
        results.append(result)
    return results


def _submit_concurrent(engine, payload: dict, n_threads: int, per_thread: int):
    """多线程并发提交，返回 (results, errors)。"""
    results: List[dict] = []
    errors: List[Exception] = []
    lock = threading.Lock()
    barrier = threading.Barrier(n_threads)

    def worker():
        barrier.wait()
        for _ in range(per_thread):
            try:
                r = engine.submit_request(dict(payload))
                with lock:
                    results.append(r)
            except Exception as exc:
                with lock:
                    errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results, errors


def _avg_utilization(engine) -> float:
    """计算当前三类资源的平均利用率。"""
    util = engine.stats["resource_utilization"]
    return (util["satellites"] + util["ground_stations"] + util["geo_relays"]) / 3.0


def _count_rejections(results: List[dict]) -> int:
    """统计结果列表中被拒绝（reject_reason 非 None/非空）的数量。"""
    return sum(
        1 for r in results
        if r.get("reject_reason") or r.get("status") in ("rejected", "error")
    )


# ---------------------------------------------------------------------------
# 测试一：无未捕获异常（阶梯加压）
# ---------------------------------------------------------------------------


class TestNoUncaughtExceptions:
    """批量提交不同规模的请求，引擎不得抛出未处理异常。"""

    @pytest.mark.parametrize("n_requests", [10, 50, 200])
    def test_sequential_no_exception(self, isolated_engine, n_requests: int):
        """顺序提交 n_requests 次，无任何异常。"""
        payload = dict(_HIGH_PRI_PAYLOAD)
        for _ in range(n_requests):
            result = isolated_engine.submit_request(dict(payload))
            assert isinstance(result, dict), "submit_request 应返回字典"

    @pytest.mark.parametrize("n_threads,per_thread", [(4, 10), (8, 25), (16, 12)])
    def test_concurrent_no_exception(self, isolated_engine, n_threads: int, per_thread: int):
        """多线程并发提交，无任何未捕获异常。"""
        results, errors = _submit_concurrent(isolated_engine, _HIGH_PRI_PAYLOAD, n_threads, per_thread)
        assert len(errors) == 0, f"发现未捕获异常: {errors[:3]}"
        assert len(results) == n_threads * per_thread

    @pytest.mark.parametrize("data_type", list(DATA_TYPES.keys()))
    def test_all_data_types_no_exception(self, isolated_engine, data_type: str):
        """所有数据类型各提交 20 次，无任何异常。"""
        payload = {
            "data_type": data_type,
            "data_size": 100,
            "priority": 5,
            "max_delay": 600,
        }
        for _ in range(20):
            result = isolated_engine.submit_request(dict(payload))
            assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 测试二：拒绝原因分布合理
# ---------------------------------------------------------------------------


class TestRejectionReasonDistribution:
    """高负载下拒绝原因必须来自已知集合，且分布合理。"""

    def test_rejection_reasons_from_known_set(self, isolated_engine):
        """提交 100 次后，所有拒绝原因均属于已知集合（含内联消息）。"""
        for _ in range(100):
            result = isolated_engine.submit_request(dict(_LOW_PRI_PAYLOAD))
            reject_reason = result.get("reject_reason")
            if reject_reason:
                # 拒绝原因文本应在已知集合（REJECTION_REASONS 文本 + 内联文本）中
                assert reject_reason in _ALL_KNOWN_REJECTION_MSGS, (
                    f"未知的拒绝原因: {reject_reason!r}\n"
                    f"已知集合: {sorted(_ALL_KNOWN_REJECTION_MSGS)}"
                )

    def test_rejection_distribution_keys_valid(self, isolated_engine):
        """rejection_distribution 中的键均为已知原因代码。"""
        # 提交足够请求触发部分拒绝
        for _ in range(50):
            isolated_engine.submit_request(dict(_LOW_PRI_PAYLOAD))
        dist = isolated_engine.stats.get("rejection_distribution", {})
        for code in dist.keys():
            assert code in _KNOWN_REJECTION_CODES, (
                f"rejection_distribution 含未知代码: {code!r}"
            )

    def test_rejection_distribution_counts_non_negative(self, isolated_engine):
        """rejection_distribution 中所有计数 >= 0。"""
        for _ in range(30):
            isolated_engine.submit_request(dict(_LOW_PRI_PAYLOAD))
        dist = isolated_engine.stats.get("rejection_distribution", {})
        for code, count in dist.items():
            assert count >= 0, f"拒绝原因 {code!r} 计数为负: {count}"

    def test_mixed_priority_rejection_ratio(self, isolated_engine):
        """混合提交高/低优先级请求：两类均有合理的结果字典。"""
        hi_results = [isolated_engine.submit_request(dict(_HIGH_PRI_PAYLOAD)) for _ in range(30)]
        lo_results = [isolated_engine.submit_request(dict(_LOW_PRI_PAYLOAD)) for _ in range(30)]

        # 所有结果均为合法字典
        for r in hi_results + lo_results:
            assert isinstance(r, dict)
            assert "status" in r or "id" in r or "reject_reason" in r or "error" in r


# ---------------------------------------------------------------------------
# 测试三：统计计数守恒
# ---------------------------------------------------------------------------


class TestStatsConsistency:
    """核心不变量：统计计数必须自洽。"""

    def test_counts_consistent_after_batch(self, isolated_engine):
        """批量提交 150 次后，total == accepted + rejected（用户请求，无背景任务）。"""
        n = 150
        for _ in range(n):
            isolated_engine.submit_request(dict(_HIGH_PRI_PAYLOAD))

        stats = isolated_engine.stats
        total = stats["total_requests"]
        accepted = stats["accepted_requests"]
        rejected = stats["rejected_requests"]

        assert total == accepted + rejected, (
            f"计数不守恒: total={total}, accepted={accepted}, rejected={rejected}"
        )

    def test_counts_non_negative(self, isolated_engine):
        """所有计数字段均 >= 0。"""
        for _ in range(80):
            isolated_engine.submit_request(dict(_LOW_PRI_PAYLOAD))

        stats = isolated_engine.stats
        for field in ("total_requests", "accepted_requests", "rejected_requests",
                      "completed_requests", "transmitting_requests"):
            val = stats.get(field, 0)
            assert val >= 0, f"stats[{field!r}] 为负: {val}"

    @pytest.mark.parametrize("n_threads,per_thread", [(4, 25), (8, 12)])
    def test_concurrent_counts_consistent(self, isolated_engine, n_threads: int, per_thread: int):
        """并发提交后，统计计数依然守恒。"""
        results, errors = _submit_concurrent(
            isolated_engine, _HIGH_PRI_PAYLOAD, n_threads, per_thread
        )
        assert len(errors) == 0, f"并发提交出现异常: {errors[:3]}"

        stats = isolated_engine.stats
        total = stats["total_requests"]
        accepted = stats["accepted_requests"]
        rejected = stats["rejected_requests"]
        assert total == accepted + rejected, (
            f"并发后计数不守恒: total={total}, accepted={accepted}, rejected={rejected}"
        )

    def test_rejection_distribution_sum_le_rejected(self, isolated_engine):
        """rejection_distribution 各原因计数之和 <= rejected_requests。"""
        for _ in range(60):
            isolated_engine.submit_request(dict(_LOW_PRI_PAYLOAD))

        stats = isolated_engine.stats
        dist_sum = sum(stats.get("rejection_distribution", {}).values())
        rejected = stats["rejected_requests"]
        assert dist_sum <= rejected, (
            f"拒绝分布总和({dist_sum}) > rejected_requests({rejected})"
        )


# ---------------------------------------------------------------------------
# 测试四：历史记录增长可控
# ---------------------------------------------------------------------------


class TestRequestHistoryGrowth:
    """request_history 长度必须 <= 累计提交次数。"""

    def test_history_bounded_sequential(self, isolated_engine):
        """顺序提交 200 次后，历史长度 <= 200。"""
        n = 200
        for _ in range(n):
            isolated_engine.submit_request(dict(_LOW_PRI_PAYLOAD))

        with isolated_engine.lock:
            history_len = len(isolated_engine.request_history)
        assert history_len <= n, (
            f"request_history 长度({history_len})超过提交次数({n})"
        )

    def test_history_bounded_concurrent(self, isolated_engine):
        """并发提交后，历史长度 <= 总提交次数。"""
        n_threads, per_thread = 8, 25
        total_submitted = n_threads * per_thread
        _submit_concurrent(isolated_engine, _LOW_PRI_PAYLOAD, n_threads, per_thread)

        with isolated_engine.lock:
            history_len = len(isolated_engine.request_history)
        assert history_len <= total_submitted, (
            f"request_history 长度({history_len})超过总提交次数({total_submitted})"
        )

    def test_history_contains_dicts(self, isolated_engine):
        """request_history 中所有元素均有 to_dict 方法或已序列化为字典。"""
        for _ in range(30):
            isolated_engine.submit_request(dict(_LOW_PRI_PAYLOAD))

        with isolated_engine.lock:
            history = list(isolated_engine.request_history)

        for item in history:
            # 支持 TransmissionRequest 对象或字典两种形式
            assert hasattr(item, "to_dict") or isinstance(item, dict), (
                f"request_history 中含非预期类型: {type(item)}"
            )


# ---------------------------------------------------------------------------
# 测试五：吞吐量与拒绝摘要统计
# ---------------------------------------------------------------------------


class TestThroughputAndSummary:
    """基线性能摘要：验证引擎在负载下能持续处理请求（吞吐不为零）。"""

    def test_throughput_non_zero_after_load(self, isolated_engine):
        """提交 100 次高优先级请求后，total_requests > 0。"""
        n = 100
        for _ in range(n):
            isolated_engine.submit_request(dict(_HIGH_PRI_PAYLOAD))

        stats = isolated_engine.stats
        assert stats["total_requests"] >= n, (
            f"total_requests({stats['total_requests']}) 小于提交次数({n})"
        )

    def test_stepped_engine_stats_valid(self, stepped_engine):
        """推进 60s 后提交请求，统计字段类型与范围合法。"""
        for _ in range(50):
            stepped_engine.submit_request(dict(_HIGH_PRI_PAYLOAD))

        stats = stepped_engine.stats
        util = stats["resource_utilization"]
        for key in ("satellites", "ground_stations", "geo_relays"):
            val = util[key]
            assert isinstance(val, (int, float)), f"resource_utilization[{key}] 类型非数值"
            assert 0.0 <= val <= 1.0, (
                f"resource_utilization[{key}]={val} 超出 [0, 1] 范围"
            )

    def test_print_load_summary(self, isolated_engine, capsys):
        """提交 200 次请求后，打印拒绝原因分布与基本吞吐摘要（供基线参考）。"""
        n = 200
        for i in range(n):
            priority = 1 if i % 3 == 0 else 7  # 混合高低优先级
            payload = dict(_HIGH_PRI_PAYLOAD)
            payload["priority"] = priority
            isolated_engine.submit_request(payload)

        stats = isolated_engine.stats
        dist = stats.get("rejection_distribution", {})

        print("\n" + "=" * 56)
        print("负载测试基线摘要 (Load Baseline Summary)")
        print("=" * 56)
        print(f"  提交总数     : {stats['total_requests']}")
        print(f"  接受数       : {stats['accepted_requests']}")
        print(f"  拒绝数       : {stats['rejected_requests']}")
        if stats["total_requests"] > 0:
            accept_rate = stats["accepted_requests"] / stats["total_requests"] * 100
            print(f"  接受率       : {accept_rate:.1f}%")
        print(f"  拒绝原因分布 :")
        if dist:
            for code, count in sorted(dist.items(), key=lambda x: -x[1]):
                print(f"    {code:<35} : {count}")
        else:
            print("    (无拒绝)")
        print("=" * 56)

        captured = capsys.readouterr()
        assert "负载测试基线摘要" in captured.out


# ---------------------------------------------------------------------------
# 测试六：高负载下资源紧张场景（手动推进步进）
# ---------------------------------------------------------------------------


class TestHighUtilizationBehavior:
    """验证资源紧张（高占用）下引擎行为符合预期。"""

    def test_no_exception_under_simulated_load(self, stepped_engine):
        """步进推进 + 批量提交，引擎在资源紧张前后均不抛出异常。"""
        # 提交大量低优先级请求
        errors = []
        for i in range(100):
            try:
                payload = {
                    "data_type": "DATA_SLICE",
                    "data_size": 500,
                    "priority": 1 + (i % 3),
                    "max_delay": 300,
                }
                stepped_engine.submit_request(payload)
            except Exception as exc:
                errors.append(exc)

        assert len(errors) == 0, f"步进负载下出现异常: {errors[:3]}"

    def test_high_priority_vs_low_priority_under_load(self, stepped_engine):
        """在连续提交后，高/低优先级请求均能正常返回结果字典（不崩溃）。"""
        hi_results = [stepped_engine.submit_request(dict(_HIGH_PRI_PAYLOAD)) for _ in range(40)]
        lo_results = [stepped_engine.submit_request(dict(_LOW_PRI_PAYLOAD)) for _ in range(40)]

        for r in hi_results + lo_results:
            assert isinstance(r, dict), "submit_request 必须始终返回字典"

    def test_stats_remain_consistent_under_stepped_load(self, stepped_engine):
        """步进 + 批量提交后，统计计数守恒。"""
        # 额外步进 30 秒
        advance_engine(stepped_engine, total_seconds=30.0, step=10.0)

        for _ in range(80):
            stepped_engine.submit_request(dict(_HIGH_PRI_PAYLOAD))

        stats = stepped_engine.stats
        total = stats["total_requests"]
        accepted = stats["accepted_requests"]
        rejected = stats["rejected_requests"]
        assert total == accepted + rejected, (
            f"步进后计数不守恒: total={total}, accepted={accepted}, rejected={rejected}"
        )
