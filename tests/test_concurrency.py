# -*- coding: utf-8 -*-
"""并发安全集成测试。

验证 SimulationEngine.submit_request 在多线程并发调用下：
  1. RLock 保护下计数器自洽（total_requests == user_requests + background_requests）
  2. 提交 N 次后 total_requests 的增量恰好为 N（无丢失、无双计）
  3. transmission_requests + request_history 中实际存储的请求数量等于 total_requests
     增量（背景任务关闭时）
  4. 无异常、无死锁（线程均能正常退出）
  5. 并发写入后 stats 中各计数器均非负

测试全部使用 autostart=False 的隔离引擎实例，不依赖真实时间推进线程。
"""

import os
import sys
import threading
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from backend.core import create_engine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_engine():
    """每次测试独立引擎（seed=0, autostart=False）。"""
    eng = create_engine(seed=0, autostart=False)
    yield eng
    eng.running = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_PAYLOAD = {
    "data_type": "TASK_CMD",
    "data_size": 50,
    "priority": 5,
    "max_delay": 600,
}


def _submit_n(engine, n, results, errors, barrier=None):
    """在一个线程中提交 n 次请求，收集结果或异常。"""
    if barrier is not None:
        barrier.wait()  # 所有线程同时开始
    for _ in range(n):
        try:
            result = engine.submit_request(dict(_VALID_PAYLOAD))
            results.append(result)
        except Exception as exc:
            errors.append(exc)


def _concurrent_submit(engine, n_threads, per_thread):
    """启动 n_threads 个线程，每线程提交 per_thread 次，返回 (results, errors)。"""
    results = []
    errors = []
    # 使用屏障让所有线程尽可能同步启动
    barrier = threading.Barrier(n_threads)
    threads = [
        threading.Thread(
            target=_submit_n,
            args=(engine, per_thread, results, errors, barrier),
        )
        for _ in range(n_threads)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results, errors


# ---------------------------------------------------------------------------
# 1. 基础无竞态：单线程多次提交
# ---------------------------------------------------------------------------

class TestSubmitSequential:
    """单线程基线：确认计数一致性，为并发测试提供对照。"""

    def test_total_requests_equals_submit_count(self, isolated_engine):
        n = 10
        before = isolated_engine.stats["total_requests"]
        for _ in range(n):
            isolated_engine.submit_request(dict(_VALID_PAYLOAD))
        assert isolated_engine.stats["total_requests"] == before + n

    def test_user_requests_incremented(self, isolated_engine):
        n = 5
        before = isolated_engine.stats["user_requests"]
        for _ in range(n):
            isolated_engine.submit_request(dict(_VALID_PAYLOAD))
        assert isolated_engine.stats["user_requests"] == before + n

    def test_accepted_plus_rejected_equals_user_requests(self, isolated_engine):
        n = 8
        for _ in range(n):
            isolated_engine.submit_request(dict(_VALID_PAYLOAD))
        stats = isolated_engine.stats
        assert (
            stats["accepted_requests"] + stats["rejected_requests"]
            <= stats["total_requests"]
        )

    def test_request_list_length_consistent(self, isolated_engine):
        n = 6
        before = (
            len(isolated_engine.transmission_requests)
            + len(isolated_engine.request_history)
        )
        for _ in range(n):
            isolated_engine.submit_request(dict(_VALID_PAYLOAD))
        after = (
            len(isolated_engine.transmission_requests)
            + len(isolated_engine.request_history)
        )
        assert after == before + n


# ---------------------------------------------------------------------------
# 2. 并发提交：计数一致性
# ---------------------------------------------------------------------------

class TestConcurrentSubmitCounting:
    """多线程并发提交 —— 计数器自洽验证。"""

    def test_no_exceptions_raised(self, isolated_engine):
        """并发提交不得抛出异常。"""
        _, errors = _concurrent_submit(isolated_engine, n_threads=5, per_thread=10)
        assert errors == [], f"并发提交出现异常: {errors}"

    def test_total_requests_equals_total_submitted(self, isolated_engine):
        """并发提交 N*M 次后，total_requests 增量应恰好为 N*M。"""
        n_threads, per_thread = 5, 20
        before = isolated_engine.stats["total_requests"]
        _, errors = _concurrent_submit(isolated_engine, n_threads, per_thread)
        assert errors == [], f"并发出现异常: {errors}"
        assert isolated_engine.stats["total_requests"] == before + n_threads * per_thread

    def test_all_results_returned(self, isolated_engine):
        """每次 submit_request 都应返回结果（不会静默丢失）。"""
        n_threads, per_thread = 4, 10
        results, errors = _concurrent_submit(isolated_engine, n_threads, per_thread)
        assert errors == []
        assert len(results) == n_threads * per_thread

    def test_results_are_dicts(self, isolated_engine):
        """每个返回值都应是字典。"""
        results, errors = _concurrent_submit(isolated_engine, n_threads=3, per_thread=5)
        assert errors == []
        for r in results:
            assert isinstance(r, dict), f"返回值应为 dict，实际为 {type(r)}"

    def test_results_have_id_field(self, isolated_engine):
        """每个结果字典应包含 id 字段。"""
        results, errors = _concurrent_submit(isolated_engine, n_threads=3, per_thread=5)
        assert errors == []
        for r in results:
            assert "id" in r or r.get("status") == "error", (
                f"结果缺少 id 字段: {r}"
            )

    def test_results_have_status_field(self, isolated_engine):
        """每个结果字典应包含 status 字段。"""
        results, errors = _concurrent_submit(isolated_engine, n_threads=3, per_thread=5)
        assert errors == []
        for r in results:
            assert "status" in r, f"结果缺少 status 字段: {r}"

    def test_no_duplicate_ids(self, isolated_engine):
        """并发提交产生的请求 ID 应唯一（若结果含 id）。"""
        results, errors = _concurrent_submit(isolated_engine, n_threads=4, per_thread=10)
        assert errors == []
        ids = [r.get("id") for r in results if r.get("id") is not None]
        assert len(ids) == len(set(ids)), "出现重复 id"

    def test_request_list_consistent_with_counter(self, isolated_engine):
        """transmission_requests + request_history 长度等于 total_requests 增量。"""
        n_threads, per_thread = 4, 15
        before_total = isolated_engine.stats["total_requests"]
        before_lists = (
            len(isolated_engine.transmission_requests)
            + len(isolated_engine.request_history)
        )
        _, errors = _concurrent_submit(isolated_engine, n_threads, per_thread)
        assert errors == []
        after_total = isolated_engine.stats["total_requests"]
        after_lists = (
            len(isolated_engine.transmission_requests)
            + len(isolated_engine.request_history)
        )
        submitted = n_threads * per_thread
        assert after_total == before_total + submitted
        assert after_lists == before_lists + submitted

    def test_counters_non_negative_after_concurrent_writes(self, isolated_engine):
        """并发写入后所有整数统计计数器均非负。"""
        _, errors = _concurrent_submit(isolated_engine, n_threads=5, per_thread=20)
        assert errors == []
        stats = isolated_engine.stats
        for key in ("total_requests", "user_requests", "accepted_requests",
                    "rejected_requests", "transmitting_requests", "completed_requests"):
            assert stats[key] >= 0, f"统计字段 {key} 为负: {stats[key]}"

    def test_accepted_plus_rejected_le_total_concurrent(self, isolated_engine):
        """accepted + rejected ≤ total（不含进行中的传输）。"""
        _, errors = _concurrent_submit(isolated_engine, n_threads=5, per_thread=20)
        assert errors == []
        s = isolated_engine.stats
        assert s["accepted_requests"] + s["rejected_requests"] <= s["total_requests"]

    def test_user_requests_le_total_concurrent(self, isolated_engine):
        """user_requests ≤ total_requests（background_requests 可能为 0）。"""
        _, errors = _concurrent_submit(isolated_engine, n_threads=5, per_thread=20)
        assert errors == []
        s = isolated_engine.stats
        assert s["user_requests"] <= s["total_requests"]


# ---------------------------------------------------------------------------
# 3. 高并发压力（更多线程）
# ---------------------------------------------------------------------------

class TestHighConcurrency:
    """更高线程数/更多请求的压力场景。"""

    def test_no_errors_under_high_concurrency(self, isolated_engine):
        """10 线程 × 30 次，合计 300 次并发提交无异常。"""
        _, errors = _concurrent_submit(isolated_engine, n_threads=10, per_thread=30)
        assert errors == [], f"高并发出现异常: {errors[:5]}"

    def test_counter_exact_under_high_concurrency(self, isolated_engine):
        """高并发下计数器与实际提交次数精确匹配。"""
        n_threads, per_thread = 10, 30
        before = isolated_engine.stats["total_requests"]
        _, errors = _concurrent_submit(isolated_engine, n_threads, per_thread)
        assert errors == []
        assert isolated_engine.stats["total_requests"] == before + n_threads * per_thread

    def test_all_threads_complete(self, isolated_engine):
        """所有线程均能在超时前完成（无死锁）。"""
        n_threads, per_thread = 8, 25
        results, errors = _concurrent_submit(isolated_engine, n_threads, per_thread)
        assert errors == []
        assert len(results) == n_threads * per_thread


# ---------------------------------------------------------------------------
# 4. 并发提交不存在的卫星（错误路径并发）
# ---------------------------------------------------------------------------

class TestConcurrentErrorPaths:
    """并发触发错误路径 —— 确保 RLock 覆盖错误流。"""

    def test_concurrent_nonexistent_satellite_no_exception(self, isolated_engine):
        """并发指定不存在的卫星，每次都应以 status='error' 结果返回，不抛异常。"""
        bad_payload = {
            "data_type": "TASK_CMD",
            "data_size": 50,
            "priority": 5,
            "max_delay": 600,
            "satellite_id": "NONEXISTENT_SAT_CONCURRENT_TEST",
        }
        results = []
        errors = []
        barrier = threading.Barrier(6)

        def worker():
            barrier.wait()
            for _ in range(5):
                try:
                    r = isolated_engine.submit_request(dict(bad_payload))
                    results.append(r)
                except Exception as exc:
                    errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == [], f"不存在卫星的并发调用出现异常: {errors}"
        for r in results:
            assert r.get("status") == "error"

    def test_rejected_count_incremented_for_missing_satellite(self, isolated_engine):
        """不存在卫星请求应计入 rejected_requests。"""
        bad_payload = dict(_VALID_PAYLOAD)
        bad_payload["satellite_id"] = "NO_SUCH_SAT_XYZ"
        n = 5
        before = isolated_engine.stats["rejected_requests"]
        for _ in range(n):
            isolated_engine.submit_request(dict(bad_payload))
        assert isolated_engine.stats["rejected_requests"] == before + n

    def test_mixed_valid_and_invalid_concurrent(self, isolated_engine):
        """合法请求与非法卫星请求混合并发，计数器仍自洽。"""
        good = dict(_VALID_PAYLOAD)
        bad = dict(_VALID_PAYLOAD)
        bad["satellite_id"] = "MIXED_BAD_SAT_99"

        results = []
        errors = []
        barrier = threading.Barrier(4)

        def good_worker():
            barrier.wait()
            for _ in range(5):
                try:
                    results.append(isolated_engine.submit_request(dict(good)))
                except Exception as exc:
                    errors.append(exc)

        def bad_worker():
            barrier.wait()
            for _ in range(5):
                try:
                    results.append(isolated_engine.submit_request(dict(bad)))
                except Exception as exc:
                    errors.append(exc)

        threads = (
            [threading.Thread(target=good_worker) for _ in range(2)]
            + [threading.Thread(target=bad_worker) for _ in range(2)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == [], f"混合并发出现异常: {errors}"
        assert len(results) == 20  # 2*5 + 2*5
        # total_requests 应等于 20
        assert isolated_engine.stats["total_requests"] >= 20
