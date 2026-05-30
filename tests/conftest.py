# -*- coding: utf-8 -*-
"""pytest 根夹具（conftest.py）。

提供可在整个 tests/ 目录中复用的夹具：
  - engine_no_threads  : autostart=False、种子固定的引擎实例（函数作用域）
  - engine_seeded      : 与上相同，但暴露种子参数供参数化测试使用

夹具均不启动后台仿真线程，确保：
  1. 测试隔离（不受真实时间推进干扰）
  2. 可在 CI 无网络、无 GPU 环境中稳定运行
  3. 引擎之间状态互不干扰（函数作用域每次新建实例）
"""
import os
import sys

# 确保 backend 包在 sys.path 中（无论从 project root 还是 tests/ 目录运行）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from backend.core import create_engine, SimulationEngine


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
