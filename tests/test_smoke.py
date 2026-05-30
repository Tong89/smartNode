# -*- coding: utf-8 -*-
"""Smoke 测试：验证 pytest 基础设施与核心导入无副作用。

本模块专注两个验收条件：
  1. 导入 backend.core 不启动后台线程、不打印日志
  2. create_engine(autostart=False) 可构造独立、确定性的引擎实例

所有测试均不依赖网络、文件系统或真实时间推进。
"""
import threading
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

# ---------------------------------------------------------------------------
# 1. 导入无副作用：重新导入 backend.core 不应新建线程
# ---------------------------------------------------------------------------

def _count_non_daemon_threads():
    return sum(1 for t in threading.enumerate() if not t.daemon)


def test_import_core_does_not_spawn_threads():
    """import backend.core 本身不应启动任何新守护线程。"""
    before = len(threading.enumerate())
    # 重复导入（已缓存），不应有新线程
    import backend.core  # noqa: F401
    after = len(threading.enumerate())
    assert after == before, (
        f"导入 backend.core 后线程数从 {before} 变为 {after}，"
        "说明模块顶层仍有副作用（线程启动）"
    )


def test_import_core_does_not_print(capsys):
    """重新导入 backend.core 不应向 stdout/stderr 输出任何内容。"""
    import importlib
    import backend.core as _core
    importlib.reload(_core)  # 强制重新执行模块顶层代码
    captured = capsys.readouterr()
    assert captured.out == "", f"stdout 不应有输出，实际：{captured.out!r}"
    assert captured.err == "", f"stderr 不应有输出，实际：{captured.err!r}"


# ---------------------------------------------------------------------------
# 2. 工厂可构造独立、确定性的引擎实例
# ---------------------------------------------------------------------------

def test_create_engine_no_autostart_returns_engine():
    """create_engine(autostart=False) 应返回 SimulationEngine 实例且不启动线程。"""
    from backend.core import create_engine, SimulationEngine

    threads_before = len(threading.enumerate())
    eng = create_engine(seed=1, autostart=False)
    threads_after = len(threading.enumerate())

    assert isinstance(eng, SimulationEngine)
    assert eng.running is False, "autostart=False 时引擎不应处于 running 状态"
    assert threads_after == threads_before, (
        f"create_engine(autostart=False) 不应启动线程（前={threads_before} 后={threads_after}）"
    )


def test_create_engine_has_satellites_and_ground_stations():
    """工厂创建的引擎应包含卫星与地面站数据。"""
    from backend.core import create_engine

    eng = create_engine(seed=7, autostart=False)
    assert len(eng.leo_satellites) > 0, "LEO 卫星列表不应为空"
    assert len(eng.ground_stations) > 0, "地面站列表不应为空"
    assert len(eng.geo_relays) > 0, "GEO 中继卫星列表不应为空"


def test_create_engine_seed_reproducibility():
    """相同种子两次创建的引擎，地面站选取结果应完全一致。"""
    from backend.core import create_engine

    a = create_engine(seed=42, autostart=False)
    b = create_engine(seed=42, autostart=False)

    ids_a = [g["id"] for g in a.ground_stations]
    ids_b = [g["id"] for g in b.ground_stations]
    assert ids_a == ids_b, "相同种子下地面站顺序应可复现"


def test_create_engine_different_seeds_may_differ():
    """不同种子创建的引擎，地面站选取结果通常不同（概率极高）。"""
    from backend.core import create_engine

    a = create_engine(seed=1, autostart=False)
    b = create_engine(seed=9999, autostart=False)

    ids_a = [g["id"] for g in a.ground_stations]
    ids_b = [g["id"] for g in b.ground_stations]
    # 注意：极低概率两种子选出相同子集，该断言在理论上可能偶发失败
    assert ids_a != ids_b, "不同种子下地面站列表应不同（种子隔离性验证）"


def test_engine_fixture_no_threads(engine_no_threads):
    """通过 conftest 夹具获得的引擎实例应处于非运行状态。"""
    eng = engine_no_threads
    assert eng.running is False
    assert hasattr(eng, "leo_satellites")
    assert hasattr(eng, "ground_stations")


def test_engine_fixture_seeded_reproducibility(engine_seeded):
    """conftest 提供的两个同种子实例应产生相同的地面站选取。"""
    a, b = engine_seeded
    assert [g["id"] for g in a.ground_stations] == [g["id"] for g in b.ground_stations]
