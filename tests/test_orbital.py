# -*- coding: utf-8 -*-
"""单元测试：OrbitalElements 轨道传播与周期/角速度数值基准。

测试目标：
  - OrbitalElements.get_mean_motion      — 角速度 (rad/s)
  - OrbitalElements.get_orbital_period   — 轨道周期 (s)
  - OrbitalElements.propagate            — (lat°, lon°, alt m) 二体传播

测试策略：
  - 使用 pytest.approx 指定容差，断言确定性数值契约。
  - 覆盖赤道-中等倾角（ISS-like）、极轨两种典型配置。
  - 覆盖 t=0、t=T/4、t=T 三个时间点（初始位置、1/4 周期、整数周期回归）。
  - 从 tests/golden/orbital_baseline.json 读取黄金基准，方便独立核实。
"""
import json
import math
import os
from datetime import datetime

import pytest

from backend.orbit import OrbitalElements

# --------------------------------------------------------------------------- #
# 辅助：加载黄金基准                                                          #
# --------------------------------------------------------------------------- #
_GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "golden", "orbital_baseline.json")


def _load_golden():
    with open(_GOLDEN_PATH, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# 夹具                                                                        #
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def golden():
    """返回黄金基准字典（模块级缓存）。"""
    return _load_golden()


@pytest.fixture
def iss_like():
    """ISS-like 圆轨道（a≈6778 km，倾角 51.6°，初始位置赤道/本初子午线）。"""
    return OrbitalElements(
        name="ISS-like",
        sat_id="iss_test",
        semi_major_axis=6778.0,
        eccentricity=0.0,
        inclination=51.6,
        raan=0.0,
        arg_perigee=0.0,
        mean_anomaly=0.0,
        epoch=datetime(2024, 1, 1, 0, 0, 0),
    )


@pytest.fixture
def polar_orbit():
    """极轨圆轨道（a=7000 km，倾角 90°）。"""
    return OrbitalElements(
        name="Polar",
        sat_id="polar_test",
        semi_major_axis=7000.0,
        eccentricity=0.0,
        inclination=90.0,
        raan=0.0,
        arg_perigee=0.0,
        mean_anomaly=0.0,
        epoch=datetime(2024, 1, 1, 0, 0, 0),
    )


# --------------------------------------------------------------------------- #
# 轨道周期测试                                                                 #
# --------------------------------------------------------------------------- #
class TestOrbitalPeriod:
    """get_orbital_period：T = 2π√(a³/μ)"""

    def test_iss_period_seconds(self, iss_like, golden):
        """ISS-like 轨道周期约 5553 s。"""
        T = iss_like.get_orbital_period()
        ref = golden["orbital_elements_iss_like"]
        assert T == pytest.approx(ref["orbital_period_s"], abs=ref["orbital_period_tol"])

    def test_polar_period_seconds(self, polar_orbit, golden):
        """极轨周期约 5829 s，高于 ISS-like（半长轴更大）。"""
        T = polar_orbit.get_orbital_period()
        ref = golden["orbital_elements_polar"]
        assert T == pytest.approx(ref["orbital_period_s"], abs=ref["orbital_period_tol"])

    def test_period_increases_with_altitude(self, iss_like, polar_orbit):
        """开普勒第三定律：半长轴越大���道周期越长。"""
        T_iss = iss_like.get_orbital_period()
        T_polar = polar_orbit.get_orbital_period()
        assert T_polar > T_iss, "a=7000 km 的极轨周期应长于 a=6778 km 的 ISS-like 轨道"

    def test_period_formula_consistency(self, iss_like):
        """T 与 n 的关系：T * n = 2π。"""
        T = iss_like.get_orbital_period()
        n = iss_like.get_mean_motion()
        assert T * n == pytest.approx(2 * math.pi, rel=1e-9)


# --------------------------------------------------------------------------- #
# 平均角速度测试                                                               #
# --------------------------------------------------------------------------- #
class TestMeanMotion:
    """get_mean_motion：n = √(μ/a³)"""

    def test_iss_mean_motion(self, iss_like, golden):
        """ISS-like 平均角速度约 0.001131 rad/s。"""
        n = iss_like.get_mean_motion()
        ref = golden["orbital_elements_iss_like"]
        assert n == pytest.approx(ref["mean_motion_rad_s"], abs=ref["mean_motion_tol"])

    def test_mean_motion_decreases_with_altitude(self, iss_like, polar_orbit):
        """半长轴越大角速度越小。"""
        n_iss = iss_like.get_mean_motion()
        n_polar = polar_orbit.get_mean_motion()
        assert n_polar < n_iss

    def test_mean_motion_units_rad_per_s(self, iss_like):
        """平均角速度单位：一个完整轨道的积分 = 2π rad。"""
        n = iss_like.get_mean_motion()
        T = iss_like.get_orbital_period()
        assert n * T == pytest.approx(2 * math.pi, rel=1e-9)


# --------------------------------------------------------------------------- #
# propagate 测试：ISS-like                                                     #
# --------------------------------------------------------------------------- #
class TestPropagateISSLike:
    """propagate：t=0 / t=T/4 / t=T 三个时间点。"""

    def test_initial_position_lat_lon(self, iss_like, golden):
        """t=0，M0=0：卫星应在赤道/本初子午线附近（过近地点）。"""
        lat, lon, alt = iss_like.propagate(0.0)
        ref = golden["orbital_elements_iss_like"]
        assert lat == pytest.approx(ref["t0_lat_deg"], abs=0.01)
        assert lon == pytest.approx(ref["t0_lon_deg"], abs=0.01)

    def test_initial_altitude(self, iss_like, golden):
        """t=0 高度约与半长轴对应的圆轨道高度一致（~400 km）。"""
        _, _, alt = iss_like.propagate(0.0)
        ref = golden["orbital_elements_iss_like"]
        assert alt == pytest.approx(ref["t0_alt_m"], abs=ref["t0_tol"])

    def test_one_period_latitude_returns(self, iss_like):
        """经过整数周期后纬度应回到与 t=0 几乎相同的值（二体无摄动）。"""
        T = iss_like.get_orbital_period()
        lat0, _, _ = iss_like.propagate(0.0)
        lat1, _, _ = iss_like.propagate(T)
        assert lat1 == pytest.approx(lat0, abs=0.01)

    def test_one_period_altitude_returns(self, iss_like):
        """整数周期后高度应恢复到初始值（圆轨道误差 < 500 m）。"""
        T = iss_like.get_orbital_period()
        _, _, alt0 = iss_like.propagate(0.0)
        _, _, alt1 = iss_like.propagate(T)
        assert alt1 == pytest.approx(alt0, abs=500.0)

    def test_quarter_period_latitude_is_near_inclination(self, iss_like):
        """t=T/4 时，纬度应接近倾角（圆轨道最高纬度 ≈ 倾角 51.6°）。"""
        T = iss_like.get_orbital_period()
        lat, _, _ = iss_like.propagate(T / 4)
        # 受地球自转影响，允许较宽容差
        assert abs(lat) == pytest.approx(iss_like.i, abs=3.0)

    def test_propagate_with_datetime(self, iss_like):
        """使用 datetime 与等效秒数传播，结果应一致。"""
        epoch = iss_like.epoch
        dt = 300.0  # 5 分钟
        t_abs = datetime(2024, 1, 1, 0, 5, 0)
        lat_s, lon_s, alt_s = iss_like.propagate(dt)
        lat_d, lon_d, alt_d = iss_like.propagate(t_abs)
        assert lat_s == pytest.approx(lat_d, abs=1e-9)
        assert lon_s == pytest.approx(lon_d, abs=1e-9)
        assert alt_s == pytest.approx(alt_d, abs=1e-3)

    def test_altitude_always_positive(self, iss_like):
        """在若干时间步长上，高度始终为正（卫星未进入大气层）。"""
        T = iss_like.get_orbital_period()
        for frac in [0, 0.1, 0.25, 0.5, 0.75, 1.0]:
            _, _, alt = iss_like.propagate(frac * T)
            assert alt > 0, f"t={frac}T 时高度应为正，实际 alt={alt}"


# --------------------------------------------------------------------------- #
# propagate 测试：极轨                                                          #
# --------------------------------------------------------------------------- #
class TestPropagatePolar:
    """极轨特有性质：t=0 纬度 = 0，t=T/4 纬度接近 +90°。"""

    def test_initial_position_equator(self, polar_orbit, golden):
        """极轨 t=0：M0=0 表示卫星在赤道升交点。"""
        lat, lon, alt = polar_orbit.propagate(0.0)
        ref = golden["orbital_elements_polar"]
        assert lat == pytest.approx(ref["t0_lat_deg"], abs=0.01)

    def test_quarter_period_near_north_pole(self, polar_orbit):
        """极轨 t=T/4：卫星应接近北极（纬度接近 +90°）。"""
        T = polar_orbit.get_orbital_period()
        lat, _, _ = polar_orbit.propagate(T / 4)
        # 允许 ±5° 容差（地球自转影响经度，但纬度仍接近极点）
        assert lat == pytest.approx(90.0, abs=5.0)

    def test_half_period_back_to_equator(self, polar_orbit):
        """极轨 t=T/2：卫星回到赤道（从南极上升）。"""
        T = polar_orbit.get_orbital_period()
        lat, _, _ = polar_orbit.propagate(T / 2)
        assert abs(lat) == pytest.approx(0.0, abs=2.0)

    def test_altitude_consistent_circular(self, polar_orbit, golden):
        """圆轨道各时刻高度应在合理范围内（WGS-84 椭球导致极点高度略高于赤道，偏差 < 25000 m）。"""
        T = polar_orbit.get_orbital_period()
        ref = golden["orbital_elements_polar"]
        expected_alt = ref["t0_alt_m"]
        for frac in [0, 0.25, 0.5, 0.75]:
            _, _, alt = polar_orbit.propagate(frac * T)
            # WGS-84 椭球在极点的高度（地表到轨道）与赤道有约 21 km 差异，故容差 25000 m
            assert alt == pytest.approx(expected_alt, abs=25000.0), (
                f"t={frac}T 时高度超出预期范围：{alt:.0f} m vs {expected_alt:.0f} m (±25000 m)"
            )


# --------------------------------------------------------------------------- #
# 黄金基准文件自洽性验证                                                       #
# --------------------------------------------------------------------------- #
class TestGoldenBaseline:
    """验证黄金基准 JSON 可正确加载且数据完整。"""

    def test_golden_file_exists(self):
        assert os.path.isfile(_GOLDEN_PATH), f"黄金基准文件不存在：{_GOLDEN_PATH}"

    def test_golden_has_required_sections(self, golden):
        required = [
            "calc_central_angle",
            "orbital_elements_iss_like",
            "orbital_elements_polar",
            "check_visibility",
            "check_geo_visibility",
        ]
        for section in required:
            assert section in golden, f"黄金基准缺少节：{section}"

    def test_iss_period_from_golden(self, golden):
        """从黄金基准直接验证 ISS-like 轨道周期。"""
        ref = golden["orbital_elements_iss_like"]
        iss = OrbitalElements(
            name="golden_iss",
            sat_id="golden_iss",
            semi_major_axis=ref["semi_major_axis_km"],
            eccentricity=ref["eccentricity"],
            inclination=ref["inclination_deg"],
            raan=ref["raan_deg"],
            arg_perigee=ref["arg_perigee_deg"],
            mean_anomaly=ref["mean_anomaly_deg"],
        )
        T = iss.get_orbital_period()
        assert T == pytest.approx(ref["orbital_period_s"], abs=ref["orbital_period_tol"])
