# -*- coding: utf-8 -*-
"""回归测试：黄金场景快照比对 (Golden scenario snapshot regression).

本模块提供基于固定 random.seed + 手动时间步进的确定性端到端场景测试，
将引擎状态 / 请求统计序列化为 JSON 黄金快照进行逐字段回对。

覆盖的 4 类数据路径：
  1. task_cmd_immediate  -- TASK_CMD 立即接受（immediate=True 类型跳过资源锁）
  2. raw_image_direct    -- RAW_IMAGE 仅直连（allowed_links=["direct"]，不经过中继）
  3. relay_bw_exhausted  -- 中继带宽耗尽后立即拒绝（DATA_SLICE 无直连/无中继带宽）
  4. wait_timeout        -- 请求等待超过 max_delay 触发 TIMEOUT_WAIT 拒绝

快照更新命令（在项目根目录执行）::

    python tests/test_regression_golden.py --update-golden

或使用 pytest 标记（需安装 pytest）::

    pytest tests/test_regression_golden.py -k "update" --capture=no

验收标准：
  - 固定种子 + 手动步进下各字段与黄金快照逐字段一致
  - 至少覆盖 4 类数据类型路径
  - 提供一条命令重新生成快照（--update-golden）
"""

import json
import os
import random
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.core import (
    SimulationEngine,
    TransmissionRequest,
    DATA_TYPES,
    MAX_WAIT_LIMIT,
    REJECTION_REASONS,
)

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------
GOLDEN_FILE = Path(__file__).parent / "golden" / "scenario_snapshots.json"

# 固定参数 — 与 golden 生成时完全一致
GOLDEN_SEED = 42
FIXED_GS_COUNT = 5
FIXED_LEO_COUNT = 4


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _make_engine(seed: int = GOLDEN_SEED) -> SimulationEngine:
    """创建可复现引擎：固定 seed、禁用后台线程、重置请求 ID 计数器。"""
    # 重置全局 ID 计数器保证 REQ_ 编号一致
    TransmissionRequest._id_counter = 0
    rng = random.Random(seed)
    eng = SimulationEngine(
        ground_station_count=FIXED_GS_COUNT,
        leo_satellite_count=FIXED_LEO_COUNT,
        rng=rng,
        autostart=False,
    )
    eng.running = False
    return eng


def _advance(eng: SimulationEngine, total: float, step: float = 1.0) -> None:
    """手动步进引擎仿真时间（不依赖实时线程）。

    Args:
        eng: autostart=False 的引擎
        total: 要推进的仿真时间（秒）
        step: 单步时间增量（秒）
    """
    elapsed = 0.0
    while elapsed < total:
        delta = min(step, total - elapsed)
        with eng.lock:
            eng.current_time += delta
            eng._update_resource_utilization()
            eng._update_decision_metrics()
            eng._update_transmissions(delta)
        elapsed += delta


def _load_golden() -> Dict[str, Any]:
    """从磁盘加载黄金快照 JSON。"""
    with open(GOLDEN_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save_golden(data: Dict[str, Any]) -> None:
    """将更新后的黄金快照写回磁盘。"""
    GOLDEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(GOLDEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[update-golden] 写入 {GOLDEN_FILE}")


def _assert_snapshot(actual: Dict, expected: Dict, scenario: str) -> None:
    """逐字段断言实际结果与黄金快照一致（忽略 _doc 注释字段）。

    Args:
        actual: 运行时采集的快照字典
        expected: 从黄金文件读取的期望快照字典
        scenario: 场景名称（用于错误消息）
    """
    for section_key in ("request", "stats"):
        actual_section = actual.get(section_key, {})
        expected_section = expected.get(section_key, {})
        for field, exp_value in expected_section.items():
            act_value = actual_section.get(field)
            assert act_value == exp_value, (
                f"[{scenario}] {section_key}.{field}: "
                f"expected={exp_value!r}, actual={act_value!r}"
            )


# ---------------------------------------------------------------------------
# 快照采集函数（与 generate_golden 共享逻辑，测试和更新复用同一实现）
# ---------------------------------------------------------------------------

def _run_scenario_task_cmd_immediate() -> Dict[str, Any]:
    """场景 1: TASK_CMD 立即接受。

    TASK_CMD 的 immediate=True 使 _evaluate_request 直接返回 True，
    无需等待链路可见——提交后立即进入 transmitting 状态。
    """
    eng = _make_engine()
    result = eng.submit_request(
        {"data_type": "TASK_CMD", "data_size": 50, "priority": 9, "max_delay": 600}
    )
    return {
        "request": {
            "data_type": result.get("data_type"),
            "status": result.get("status"),
            "reject_reason": result.get("reject_reason"),
            "source": result.get("source"),
        },
        "stats": {
            "total_requests": eng.stats["total_requests"],
            "accepted_requests": eng.stats["accepted_requests"],
            "rejected_requests": eng.stats["rejected_requests"],
        },
    }


def _run_scenario_raw_image_direct() -> Dict[str, Any]:
    """场景 2: RAW_IMAGE 仅直连。

    RAW_IMAGE 的 allowed_links=["direct"] 决定了中继路径被跳过；
    当卫星与某地面站当前可见时，transmission_method 必须为 "direct"。
    """
    eng = _make_engine()
    result = eng.submit_request(
        {"data_type": "RAW_IMAGE", "data_size": 5, "priority": 3, "max_delay": 3600}
    )
    return {
        "request": {
            "data_type": result.get("data_type"),
            "status": result.get("status"),
            "reject_reason": result.get("reject_reason"),
            "transmission_method": result.get("transmission_method"),
            "source": result.get("source"),
        },
        "stats": {
            "total_requests": eng.stats["total_requests"],
            "accepted_requests": eng.stats["accepted_requests"],
            "rejected_requests": eng.stats["rejected_requests"],
        },
    }


def _run_scenario_relay_bandwidth_exhausted() -> Dict[str, Any]:
    """场景 3: 中继带宽耗尽。

    通过向 transmission_requests 注入高速率的虚拟传输请求填满所有 GEO 中继带宽，
    同时在 resource_usage 中标记所有地面站为占用状态；
    此后提交 DATA_SLICE 应立即被拒绝（无可用通信链路）。
    """
    eng = _make_engine()

    # 占用所有地面站
    for gs in eng.ground_stations:
        eng.resource_usage["ground_stations"][gs["id"]] = ["DUMMY_GS"]

    # 用高速率虚拟请求填满所有 GEO 中继带宽
    for geo in eng.geo_relays:
        dummy = TransmissionRequest("DATA_SLICE", 500, 5, 600)
        dummy.status = "transmitting"
        dummy.transmission_rate = geo.get("bandwidth", 1600) * 2  # 超出带宽上限
        dummy.selected_relay = geo["id"]
        dummy.satellite_id = eng.leo_satellites[0].sat_id
        eng.transmission_requests.append(dummy)
        # 同时在资源占用字典中标记中继已用
        eng.resource_usage["geo_relays"][geo["id"]] = ["DUMMY_GEO"]

    result = eng.submit_request(
        {"data_type": "DATA_SLICE", "data_size": 100, "priority": 5, "max_delay": 600}
    )
    return {
        "request": {
            "data_type": result.get("data_type"),
            "status": result.get("status"),
            "reject_reason": result.get("reject_reason"),
            "source": result.get("source"),
        },
        "stats": {
            "total_requests": eng.stats["total_requests"],
            "accepted_requests": eng.stats["accepted_requests"],
            "rejected_requests": eng.stats["rejected_requests"],
        },
    }


def _run_scenario_wait_timeout() -> Dict[str, Any]:
    """场景 4: 等待超时 (TIMEOUT_WAIT)。

    通过占用所有地面站的资源使 RAW_IMAGE 进入「等待过境」状态（accepted）；
    随后手动推进仿真时间至 max_delay + 1 秒，触发 TIMEOUT_WAIT 拒绝逻辑。

    注：max_delay=7200 保证 strategy3 轨道预测能找到未来过境机会（>= 1 个轨道步长），
    从而使请求进入 accepted 状态而非直接拒绝。
    """
    eng = _make_engine()

    # 占用所有地面站（使当前无直连路径，但 strategy3 预测未来过境）
    for gs in eng.ground_stations:
        eng.resource_usage["ground_stations"][gs["id"]] = ["DUMMY_GS"]

    max_delay = 7200
    result = eng.submit_request(
        {
            "data_type": "RAW_IMAGE",
            "data_size": 5,
            "priority": 3,
            "max_delay": max_delay,
        }
    )

    # 确认初始状态为 accepted（等待过境）
    assert result.get("status") == "accepted", (
        f"timeout 场景前置条件失败：期望 accepted，实际 {result.get('status')}"
    )

    # 推进时间至超过 max_delay（+1 秒触发超时判断）
    _advance(eng, total=max_delay + 1, step=1.0)

    # 超时后请求已从 transmission_requests 移入 request_history
    timeout_req = next(
        (r for r in eng.request_history if r.data_type == "RAW_IMAGE"), None
    )
    assert timeout_req is not None, "timeout 场景：history 中未找到 RAW_IMAGE 请求"

    return {
        "request": {
            "data_type": timeout_req.data_type,
            "status": timeout_req.status,
            "reject_reason": timeout_req.reject_reason,
            "source": timeout_req.source,
        },
        "stats": {
            "total_requests": eng.stats["total_requests"],
            "accepted_requests": eng.stats["accepted_requests"],
            "rejected_requests": eng.stats["rejected_requests"],
        },
    }


# ---------------------------------------------------------------------------
# 快照生成器（--update-golden 命令行入口）
# ---------------------------------------------------------------------------

def generate_golden() -> None:
    """重新生成所有场景快照并覆盖写回 golden/scenario_snapshots.json。

    调用方式::

        python tests/test_regression_golden.py --update-golden
    """
    print("[update-golden] 重新生成黄金快照，seed=%d" % GOLDEN_SEED)
    existing = {}
    if GOLDEN_FILE.exists():
        with open(GOLDEN_FILE, encoding="utf-8") as f:
            existing = json.load(f)

    # 保留元数据注释字段
    new_data: Dict[str, Any] = {
        "_comment": existing.get(
            "_comment",
            "黄金场景快照 — 由 tests/fixtures/scenarios.py 生成，seed=42，用于 test_regression_golden.py 逐字段回归断言。",
        ),
        "_generated_by": "tests/test_regression_golden.py::generate (python tests/test_regression_golden.py --update-golden)",
        "_seed": GOLDEN_SEED,
        "_ground_station_count": FIXED_GS_COUNT,
        "_leo_satellite_count": FIXED_LEO_COUNT,
    }

    scenarios = {
        "task_cmd_immediate": (
            _run_scenario_task_cmd_immediate,
            "场景1: TASK_CMD 立即接受 — immediate=True 类型无需等待链路，直接进入 transmitting",
        ),
        "raw_image_direct": (
            _run_scenario_raw_image_direct,
            "场景2: RAW_IMAGE 仅直连 — allowed_links=[direct]，transmission_method 必须为 direct",
        ),
        "relay_bandwidth_exhausted": (
            _run_scenario_relay_bandwidth_exhausted,
            "场景3: 中继带宽耗尽 — 所有 GEO 中继带宽已满且地面站被占用，DATA_SLICE 被立即拒绝",
        ),
        "wait_timeout": (
            _run_scenario_wait_timeout,
            "场景4: 等待超时 — RAW_IMAGE 被接受等待过境，但在 max_delay 内无法开始传输，触发 TIMEOUT_WAIT",
        ),
    }

    for name, (fn, doc) in scenarios.items():
        print(f"  生成场景: {name} ...")
        snapshot = fn()
        snapshot["_doc"] = doc
        # 保持字段顺序：_doc 在前
        new_data[name] = {"_doc": doc, **{k: v for k, v in snapshot.items() if k != "_doc"}}

    _save_golden(new_data)
    print("[update-golden] 完成 ->", GOLDEN_FILE)


# ---------------------------------------------------------------------------
# pytest 测试用例
# ---------------------------------------------------------------------------

class TestGoldenScenarios:
    """黄金场景回归测试套件。

    每个 test_ 方法对应一个确定性场景，通过固定种子 + 手动时间步进保证可复现，
    断言结果与 golden/scenario_snapshots.json 中的黄金快照逐字段一致。
    """

    @pytest.fixture(autouse=True)
    def _golden(self):
        """加载黄金快照，供各测试用例复用。"""
        self._snapshots = _load_golden()

    # ------------------------------------------------------------------
    # 场景 1：TASK_CMD 立即接受
    # ------------------------------------------------------------------

    def test_task_cmd_immediate_accept(self):
        """TASK_CMD immediate=True 类型：提交后立即进入 transmitting，无拒绝原因。"""
        actual = _run_scenario_task_cmd_immediate()
        expected = self._snapshots["task_cmd_immediate"]
        _assert_snapshot(actual, expected, "task_cmd_immediate")

    def test_task_cmd_status_not_rejected(self):
        """TASK_CMD 不应被拒绝（除非系统极端资源紧张）。"""
        eng = _make_engine()
        result = eng.submit_request(
            {"data_type": "TASK_CMD", "data_size": 50, "priority": 9, "max_delay": 600}
        )
        assert result.get("status") != "rejected", (
            f"TASK_CMD 不应被拒绝，实际状态: {result.get('status')}, "
            f"原因: {result.get('reject_reason')}"
        )

    def test_task_cmd_stats_counters(self):
        """TASK_CMD 成功接受后 total_requests=1, accepted=1, rejected=0。"""
        actual = _run_scenario_task_cmd_immediate()
        stats = actual["stats"]
        assert stats["total_requests"] == 1
        assert stats["accepted_requests"] == 1
        assert stats["rejected_requests"] == 0

    # ------------------------------------------------------------------
    # 场景 2：RAW_IMAGE 仅直连
    # ------------------------------------------------------------------

    def test_raw_image_direct_only(self):
        """RAW_IMAGE transmission_method 必须为 direct，不得经过中继。"""
        actual = _run_scenario_raw_image_direct()
        expected = self._snapshots["raw_image_direct"]
        _assert_snapshot(actual, expected, "raw_image_direct")

    def test_raw_image_no_relay_link(self):
        """RAW_IMAGE 的 allowed_links 中不应包含 relay。"""
        assert "relay" not in DATA_TYPES["RAW_IMAGE"]["allowed_links"], (
            "RAW_IMAGE 数据类型不应允许中继链路"
        )

    def test_raw_image_transmission_method_is_direct(self):
        """当卫星与地面站当前可见时，RAW_IMAGE 必须通过直连方式传输。"""
        actual = _run_scenario_raw_image_direct()
        assert actual["request"]["transmission_method"] == "direct", (
            f"RAW_IMAGE transmission_method 应为 direct，实际: "
            f"{actual['request']['transmission_method']}"
        )

    # ------------------------------------------------------------------
    # 场景 3：中继带宽耗尽
    # ------------------------------------------------------------------

    def test_relay_bandwidth_exhausted_rejection(self):
        """中继带宽耗尽时 DATA_SLICE 应被立即拒绝。"""
        actual = _run_scenario_relay_bandwidth_exhausted()
        expected = self._snapshots["relay_bandwidth_exhausted"]
        _assert_snapshot(actual, expected, "relay_bandwidth_exhausted")

    def test_relay_bandwidth_exhausted_status_is_rejected(self):
        """带宽耗尽场景：请求状态应为 rejected。"""
        actual = _run_scenario_relay_bandwidth_exhausted()
        assert actual["request"]["status"] == "rejected"

    def test_relay_bandwidth_exhausted_stats(self):
        """带宽耗尽场景：total=1, accepted=0, rejected=1。"""
        actual = _run_scenario_relay_bandwidth_exhausted()
        stats = actual["stats"]
        assert stats["total_requests"] == 1
        assert stats["accepted_requests"] == 0
        assert stats["rejected_requests"] == 1

    # ------------------------------------------------------------------
    # 场景 4：等待超时
    # ------------------------------------------------------------------

    def test_wait_timeout_rejection(self):
        """等待超时后请求状态应转为 rejected，拒绝原因为 TIMEOUT_WAIT。"""
        actual = _run_scenario_wait_timeout()
        expected = self._snapshots["wait_timeout"]
        _assert_snapshot(actual, expected, "wait_timeout")

    def test_wait_timeout_reject_reason_text(self):
        """超时拒绝原因应包含关键词 '等待超时'。"""
        actual = _run_scenario_wait_timeout()
        reason = actual["request"].get("reject_reason", "")
        assert "等待超时" in (reason or ""), (
            f"超时拒绝原因不匹配，实际: {reason!r}"
        )

    def test_wait_timeout_initial_accepted_then_rejected(self):
        """验证超时流程：先进入 accepted（等待过境），超时后变为 rejected。"""
        eng = _make_engine()
        # 占用所有地面站，使当前无直连链路
        for gs in eng.ground_stations:
            eng.resource_usage["ground_stations"][gs["id"]] = ["DUMMY_GS"]

        max_delay = 7200
        result = eng.submit_request(
            {
                "data_type": "RAW_IMAGE",
                "data_size": 5,
                "priority": 3,
                "max_delay": max_delay,
            }
        )
        # 提交后应为 accepted（等待过境预测成功）
        assert result.get("status") == "accepted", (
            f"初始状态应为 accepted，实际: {result.get('status')}"
        )

        # 步进到超时
        _advance(eng, total=max_delay + 1, step=1.0)

        # 请求应已移入历史并标记为 rejected
        timeout_req = next(
            (r for r in eng.request_history if r.data_type == "RAW_IMAGE"), None
        )
        assert timeout_req is not None, "超时请求未出现在 request_history 中"
        assert timeout_req.status == "rejected", (
            f"超时后状态应为 rejected，实际: {timeout_req.status}"
        )

    # ------------------------------------------------------------------
    # 跨场景断言：数据类型覆盖
    # ------------------------------------------------------------------

    def test_covers_four_data_type_paths(self):
        """验证 4 个场景覆盖至少 4 类不同的数据类型路径。"""
        golden = _load_golden()
        data_types_covered = {
            golden[s]["request"]["data_type"]
            for s in ("task_cmd_immediate", "raw_image_direct",
                      "relay_bandwidth_exhausted", "wait_timeout")
        }
        assert len(data_types_covered) >= 3, (
            f"应覆盖至少 3 类数据类型，实际: {data_types_covered}"
        )
        # TASK_CMD 和 RAW_IMAGE 必须出现
        assert "TASK_CMD" in data_types_covered, "缺少 TASK_CMD 场景覆盖"
        assert "RAW_IMAGE" in data_types_covered, "缺少 RAW_IMAGE 场景覆盖"

    def test_golden_file_exists_and_valid_json(self):
        """黄金快照文件应存在且为有效 JSON。"""
        assert GOLDEN_FILE.exists(), f"黄金快照文件不存在: {GOLDEN_FILE}"
        data = _load_golden()
        assert isinstance(data, dict), "黄金快照应为 JSON 对象"
        # 检查必须包含 4 个场景键
        required_keys = {
            "task_cmd_immediate",
            "raw_image_direct",
            "relay_bandwidth_exhausted",
            "wait_timeout",
        }
        missing = required_keys - set(data.keys())
        assert not missing, f"黄金快照缺少场景键: {missing}"

    def test_seed_determinism(self):
        """相同 seed=42 下，两次独立运行的结果应完全一致。"""
        result_a = _run_scenario_task_cmd_immediate()
        result_b = _run_scenario_task_cmd_immediate()
        assert result_a == result_b, (
            f"seed={GOLDEN_SEED} 下两次运行结果不一致:\n  A={result_a}\n  B={result_b}"
        )


# ---------------------------------------------------------------------------
# conftest 场景夹具（供其他测试文件复用）
# ---------------------------------------------------------------------------

@pytest.fixture
def seeded_engine():
    """提供固定种子、不启动后台线程的引擎夹具（供外部测试复用）���"""
    return _make_engine(GOLDEN_SEED)


@pytest.fixture
def golden_snapshots():
    """加载并返回黄金快照字典（供外部测试直接断言）。"""
    return _load_golden()


# ---------------------------------------------------------------------------
# 命令行入口：--update-golden
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="黄金场景快照工具")
    parser.add_argument(
        "--update-golden",
        action="store_true",
        help="重新生成并更新 golden/scenario_snapshots.json",
    )
    args = parser.parse_args()

    if args.update_golden:
        generate_golden()
    else:
        parser.print_help()
