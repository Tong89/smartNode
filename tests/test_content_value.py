# -*- coding: utf-8 -*-
"""单元测试：ContentTask.get_dynamic_value 数据价值衰减模型。

测试目标：
  - ContentTask.get_dynamic_value — 指数衰减 V(t) = base_value * exp(-beta * (t - t0))

测试策略：
  - 初始值：t=creation_time 时返回 base_value。
  - 单调性：价值随时间推进单调下降。
  - 精确衰减：在已知 beta 下，指定时间点处数值与公式吻合（rel=1e-9）。
  - 各类型（SAR/OPTICAL/IOT/CONTROL 等）的 beta/base_value 配置验证。
  - DATA_TYPES 配置下的内置类型（TASK_CMD/INTEL/DATA_SLICE/RAW_IMAGE）亦纳入测试。
  - 半衰期验证：t=ln(2)/beta 时价值恰为 base_value/2。
"""
import math

import pytest

from backend.core import ContentTask, DATA_TYPES


# --------------------------------------------------------------------------- #
# 辅助                                                                         #
# --------------------------------------------------------------------------- #

def _make_task(task_type: str, creation_time: float = 0.0) -> ContentTask:
    """构造 ContentTask 并设置创建时刻。"""
    task = ContentTask(task_type)
    task.creation_time = creation_time
    return task


# --------------------------------------------------------------------------- #
# 基本行为                                                                     #
# --------------------------------------------------------------------------- #

class TestGetDynamicValueBasic:
    """get_dynamic_value 基础契约。"""

    def test_at_creation_time_equals_base_value(self):
        """t=creation_time 时，价值等于 base_value（dt=0，exp(0)=1）。"""
        task = _make_task("SAR", creation_time=100.0)
        v = task.get_dynamic_value(100.0)
        assert v == pytest.approx(task.base_value, rel=1e-9)

    def test_value_decreases_over_time(self):
        """价值随时间推进单调下降。"""
        task = _make_task("OPTICAL", creation_time=0.0)
        v0 = task.get_dynamic_value(0.0)
        v1 = task.get_dynamic_value(10.0)
        v2 = task.get_dynamic_value(100.0)
        assert v0 > v1 > v2

    def test_value_never_negative(self):
        """任意时刻价值不为负（指数函数恒正）。

        注：使用低衰减率 IOT 类型（beta=0.001），避免浮点下溢导致 exp() 为 0.0。
        """
        task = _make_task("IOT", creation_time=0.0)
        for dt in [0, 1, 10, 100, 1000, 5000]:
            v = task.get_dynamic_value(dt)
            assert v > 0, f"t={dt} 时价值应为正，实际 v={v}"

    def test_value_always_le_base_value(self):
        """任意时刻价值不超过初始价值（衰减不增长）。"""
        task = _make_task("IOT", creation_time=50.0)
        base = task.base_value
        for t in [50.0, 60.0, 100.0, 500.0]:
            v = task.get_dynamic_value(t)
            assert v <= base + 1e-12, f"t={t} 时价值 {v} 超过 base_value {base}"


# --------------------------------------------------------------------------- #
# 精确衰减数值                                                                 #
# --------------------------------------------------------------------------- #

class TestGetDynamicValueNumerics:
    """与公式 base_value * exp(-beta * dt) 精确对齐。"""

    def test_exact_decay_sar(self):
        """SAR 类型：beta=0.15，base_value=100.0；dt=5 时精确验证。"""
        task = _make_task("SAR", creation_time=0.0)
        dt = 5.0
        expected = task.base_value * math.exp(-task.beta * dt)
        v = task.get_dynamic_value(dt)
        assert v == pytest.approx(expected, rel=1e-9)

    def test_exact_decay_optical(self):
        """OPTICAL 类型：beta=0.05，base_value=80.0；dt=20 时精确验证。"""
        task = _make_task("OPTICAL", creation_time=0.0)
        dt = 20.0
        expected = task.base_value * math.exp(-task.beta * dt)
        v = task.get_dynamic_value(dt)
        assert v == pytest.approx(expected, rel=1e-9)

    def test_exact_decay_control(self):
        """CONTROL 类型：beta=0.5，base_value=150.0；dt=2 时精确验证。"""
        task = _make_task("CONTROL", creation_time=0.0)
        dt = 2.0
        expected = task.base_value * math.exp(-task.beta * dt)
        v = task.get_dynamic_value(dt)
        assert v == pytest.approx(expected, rel=1e-9)

    def test_exact_decay_iot(self):
        """IOT 类型：beta=0.001，base_value=40.0；dt=1000 时精确验证。"""
        task = _make_task("IOT", creation_time=0.0)
        dt = 1000.0
        expected = task.base_value * math.exp(-task.beta * dt)
        v = task.get_dynamic_value(dt)
        assert v == pytest.approx(expected, rel=1e-9)

    def test_half_life_sar(self):
        """SAR 半衰期 t_half = ln(2)/beta：此时价值应为 base_value/2。"""
        task = _make_task("SAR", creation_time=0.0)
        t_half = math.log(2) / task.beta
        v = task.get_dynamic_value(t_half)
        assert v == pytest.approx(task.base_value / 2.0, rel=1e-6)

    def test_half_life_optical(self):
        """OPTICAL 半衰期验证。"""
        task = _make_task("OPTICAL", creation_time=0.0)
        t_half = math.log(2) / task.beta
        v = task.get_dynamic_value(t_half)
        assert v == pytest.approx(task.base_value / 2.0, rel=1e-6)

    def test_double_time_squared_decay(self):
        """两倍时间时，价值为初始值的 exp(-2*beta*T_1) = v1^2 / base_value。"""
        task = _make_task("SAR", creation_time=0.0)
        dt1, dt2 = 5.0, 10.0
        v1 = task.get_dynamic_value(dt1)
        v2 = task.get_dynamic_value(dt2)
        # exp(-beta*2*T) = (exp(-beta*T))^2
        assert v2 == pytest.approx(v1 ** 2 / task.base_value, rel=1e-9)

    def test_creation_time_offset(self):
        """creation_time=500 时，t=600 的价值等同于 creation_time=0、t=100 的价值。"""
        task_offset = _make_task("OPTICAL", creation_time=500.0)
        task_zero = _make_task("OPTICAL", creation_time=0.0)
        v_offset = task_offset.get_dynamic_value(600.0)
        v_zero = task_zero.get_dynamic_value(100.0)
        assert v_offset == pytest.approx(v_zero, rel=1e-9)


# --------------------------------------------------------------------------- #
# DATA_TYPES 配置一致性                                                        #
# --------------------------------------------------------------------------- #

class TestContentTaskDataTypesConfig:
    """验证 ContentTask 读取 DATA_TYPES 时 beta 与 base_value 与配置一致。"""

    @pytest.mark.parametrize("data_type", list(DATA_TYPES.keys()))
    def test_beta_matches_data_types_config(self, data_type):
        """ContentTask 的 beta 应与 DATA_TYPES[data_type]['beta'] 一致。"""
        task = _make_task(data_type)
        expected_beta = DATA_TYPES[data_type]["beta"]
        assert task.beta == pytest.approx(expected_beta, rel=1e-12)

    @pytest.mark.parametrize("data_type", list(DATA_TYPES.keys()))
    def test_base_value_matches_data_types_config(self, data_type):
        """ContentTask 的 base_value 应与 DATA_TYPES[data_type]['base_value'] 一致。"""
        task = _make_task(data_type)
        expected_base = DATA_TYPES[data_type]["base_value"]
        assert task.base_value == pytest.approx(expected_base, rel=1e-12)

    @pytest.mark.parametrize("data_type", list(DATA_TYPES.keys()))
    def test_initial_value_matches_base(self, data_type):
        """t=0 时 get_dynamic_value 返回值应等于 base_value。"""
        task = _make_task(data_type, creation_time=0.0)
        v = task.get_dynamic_value(0.0)
        assert v == pytest.approx(task.base_value, rel=1e-9)


# --------------------------------------------------------------------------- #
# 兜底类型（非 DATA_TYPES 键）                                                #
# --------------------------------------------------------------------------- #

class TestContentTaskFallbackTypes:
    """验证不在 DATA_TYPES 中的类型使用 params 字典兜底。"""

    @pytest.mark.parametrize("task_type,expected_beta,expected_base", [
        ("SAR",      0.15, 100.0),
        ("OPTICAL",  0.05,  80.0),
        ("IOT",     0.001,  40.0),
        ("CONTROL",  0.5,  150.0),
        ("INFRARED", 0.03,  70.0),
        ("COMM",     0.02,  60.0),
    ])
    def test_fallback_beta_and_base(self, task_type, expected_beta, expected_base):
        """已知兜底类型的 beta/base_value 应与 params 字典匹配。"""
        # 仅对不在 DATA_TYPES 中的类型测试兜底逻辑
        if task_type in DATA_TYPES:
            pytest.skip(f"{task_type} 已在 DATA_TYPES 中，不走兜底路径")
        task = _make_task(task_type)
        assert task.beta == pytest.approx(expected_beta, rel=1e-12)
        assert task.base_value == pytest.approx(expected_base, rel=1e-12)

    def test_unknown_type_uses_default(self):
        """完全未知的类型应使用最终默认值 (beta=0.02, base_value=60.0)。"""
        task = _make_task("TOTALLY_UNKNOWN_TYPE_XYZ")
        assert task.beta == pytest.approx(0.02, rel=1e-12)
        assert task.base_value == pytest.approx(60.0, rel=1e-12)

    def test_unknown_type_decay(self):
        """使用兜底默认值的未知类型，其 get_dynamic_value 仍应正确指数衰减。"""
        task = _make_task("TOTALLY_UNKNOWN_TYPE_XYZ", creation_time=0.0)
        dt = 10.0
        expected = task.base_value * math.exp(-task.beta * dt)
        v = task.get_dynamic_value(dt)
        assert v == pytest.approx(expected, rel=1e-9)


# --------------------------------------------------------------------------- #
# 高衰减率场景（CONTROL 类型，beta=0.5）                                       #
# --------------------------------------------------------------------------- #

class TestHighDecayRate:
    """CONTROL 类型 beta=0.5 下的快速衰减场景。"""

    def test_control_decay_sharp(self):
        """CONTROL 类型 10 秒后价值应衰减至约 base_value * exp(-5) ≈ 1%。"""
        task = _make_task("CONTROL", creation_time=0.0)
        v10 = task.get_dynamic_value(10.0)
        expected = task.base_value * math.exp(-0.5 * 10.0)
        assert v10 == pytest.approx(expected, rel=1e-9)
        # 10 秒后保留约 0.67% 初始价值
        assert v10 < task.base_value * 0.01

    def test_control_near_zero_after_long_time(self):
        """CONTROL 类型经过足够长时间后价值应趋近于零。"""
        task = _make_task("CONTROL", creation_time=0.0)
        v_late = task.get_dynamic_value(100.0)
        assert v_late < 1e-15
