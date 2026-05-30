# -*- coding: utf-8 -*-
"""pytest 根夹具（conftest.py）。

提供可在整个 tests/ 目录中复用的夹具：
  - engine_no_threads       : autostart=False、种子固定的引擎实例（函数作用域）
  - engine_seeded           : 与上相同，但暴露种子参数供参数化测试使用
  - flask_client            : 注入干净引擎的 Flask test_client（函数作用域）
  - flask_client_engine     : 同 flask_client，额外暴露底层引擎实例
  - scenario_engine         : 固定 seed=42 的场景引擎夹具（供回归测试复用）
  - golden_scenario_snapshots: 加载 golden/scenario_snapshots.json 供断言

夹具均不启动后台仿真线程，确保：
  1. 测试隔离（不受真实时间推进干扰）
  2. 可在 CI 无网络、无 GPU 环境中稳定运行
  3. 引擎之间状态互不干扰（函数作用域每次新建实例）
"""
import json
import os
import random
import sys
from pathlib import Path

# 确保 backend 包在 sys.path 中（无论从 project root 还是 tests/ 目录运行）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from backend.core import create_engine, SimulationEngine, TransmissionRequest

# 黄金快照文件路径（供回归夹具使用）
_GOLDEN_FILE = Path(__file__).parent / "golden" / "scenario_snapshots.json"

# 固定种子（与 test_regression_golden.py 保持一致）
_GOLDEN_SEED = 42
_GOLDEN_GS_COUNT = 5
_GOLDEN_LEO_COUNT = 4


@pytest.fixture
def engine_no_threads():
    """使用固定种子、不启动后台线程的引擎，适合纯功能单测。"""
    eng = create_engine(seed=0, autostart=False)
    yield eng
    # 确保即使测试中意外设置了 running=True 也能安全清理
    eng.running = False


@pytest.fixture
def engine_seeded():
    """与 engine_no_threads 相同，但以工厂默认参数创建，供需要两个独立实例的测试使用。"""
    a = create_engine(seed=42, autostart=False)
    b = create_engine(seed=42, autostart=False)
    yield a, b
    a.running = False
    b.running = False


@pytest.fixture
def flask_client():
    """注入干净引擎（seed=0, autostart=False）的 Flask test_client。

    替换 api.simulation_engine 后在函数作用域内运行测试，测试结束后恢复原始引擎，
    保证测试间无状态污染。适合 API 集成测试中只需 client、不需直接操作引擎的场景。
    """
    import backend.api as api_module

    eng = create_engine(seed=0, autostart=False)
    original = api_module.simulation_engine
    api_module.simulation_engine = eng
    api_module.app.config["TESTING"] = True
    try:
        with api_module.app.test_client() as c:
            yield c
    finally:
        eng.running = False
        api_module.simulation_engine = original


@pytest.fixture
def scenario_engine():
    """固定 seed=42 的场景引擎夹具（用于回归测试）。

    - 使用与黄金快照生成时相同的参数（seed=42, gs=5, leo=4）
    - 不启动后台线程，可通过手动步进推进仿真时间
    - 每次请求前重置 TransmissionRequest ID 计数器保证可复现性

    Yields:
        SimulationEngine: 固定种子、不启动线程的引擎实例
    """
    TransmissionRequest._id_counter = 0
    rng = random.Random(_GOLDEN_SEED)
    eng = SimulationEngine(
        ground_station_count=_GOLDEN_GS_COUNT,
        leo_satellite_count=_GOLDEN_LEO_COUNT,
        rng=rng,
        autostart=False,
    )
    eng.running = False
    yield eng
    eng.running = False


@pytest.fixture
def golden_scenario_snapshots():
    """从 golden/scenario_snapshots.json 加载并返回黄金快照字典。

    供需要直接断言黄金数据的测试使用，避免重复加载文件。

    Returns:
        dict: 黄金场景快照字典（包含 task_cmd_immediate、raw_image_direct 等键）
    """
    if not _GOLDEN_FILE.exists():
        pytest.skip(f"黄金快照文件不存在: {_GOLDEN_FILE}")
    with open(_GOLDEN_FILE, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def flask_client_engine():
    """与 flask_client 相同，但同时暴露底层引擎，供需要断言引擎内部状态的测试使用。

    Yields:
        (client, engine): Flask test_client 与对应的 SimulationEngine 实例。
    """
    import backend.api as api_module

    eng = create_engine(seed=0, autostart=False)
    original = api_module.simulation_engine
    api_module.simulation_engine = eng
    api_module.app.config["TESTING"] = True
    try:
        with api_module.app.test_client() as c:
            yield c, eng
    finally:
        eng.running = False
        api_module.simulation_engine = original
