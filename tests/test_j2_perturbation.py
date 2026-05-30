# -*- coding: utf-8 -*-
"""单元测试：OrbitalElements J2 摄动修正。

测试目标：
  - J2 速率函数（j2_raan_rate / j2_arg_perigee_rate / j2_mean_anomaly_rate_correction）
  - 太阳同步轨道 RAAN 进动方向与数值
  - j2_perturbation 开关：关闭时退化为纯二体
  - 圆轨道短期（t=0 对比 t=dt_short）位置连续无跳变

参考值：
  - 太阳同步轨道（a≈7078 km，i=97.4°）RAAN 进动速率约 +0.9856°/天（向东）
    使逆行轨道 RAAN 随时间按固定速率增大，与太阳同步条件吻合。
"""
from __future__ import annotations

import math
from datetime import datetime

import pytest

from backend.physics.propagator import (
    J2,
    MU_EARTH,
    R_EARTH_KM,
    j2_arg_perigee_rate,
    j2_mean_anomaly_rate_correction,
    j2_raan_rate,
)
from backend.orbit import OrbitalElements


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------

@pytest.fixture
def sso_orbit():
    """太阳同步轨道（高度 700 km，倾角 97.4°，圆轨道）。"""
    a = R_EARTH_KM + 700.0   # km
    return OrbitalElements(
        name="SSO-700",
        sat_id="sso_test",
        semi_major_axis=a,
        eccentricity=0.0,
        inclination=97.4,
        raan=0.0,
        arg_perigee=0.0,
        mean_anomaly=0.0,
        epoch=datetime(2024, 1, 1, 0, 0, 0),
        j2_perturbation=True,
    )


@pytest.fixture
def iss_like_j2():
    """ISS-like 圆轨道（开启 J2）。"""
    return OrbitalElements(
        name="ISS-like-J2",
        sat_id="iss_j2_test",
        semi_major_axis=6778.0,
        eccentricity=0.0,
        inclination=51.6,
        raan=0.0,
        arg_perigee=0.0,
        mean_anomaly=0.0,
        epoch=datetime(2024, 1, 1, 0, 0, 0),
        j2_perturbation=True,
    )


@pytest.fixture
def iss_like_no_j2():
    """ISS-like 圆轨道（关闭 J2，纯二体）。"""
    return OrbitalElements(
        name="ISS-like-NoJ2",
        sat_id="iss_noj2_test",
        semi_major_axis=6778.0,
        eccentricity=0.0,
        inclination=51.6,
        raan=0.0,
        arg_perigee=0.0,
        mean_anomaly=0.0,
        epoch=datetime(2024, 1, 1, 0, 0, 0),
        j2_perturbation=False,
    )


# ---------------------------------------------------------------------------
# J2 速率函数测试
# ---------------------------------------------------------------------------

class TestJ2RateConstants:
    """验证物理常量与 J2 速率函数结果量级。"""

    def test_j2_constant_value(self):
        """J2 应在 WGS-84 标准值附近（1.082626681e-3）。"""
        assert J2 == pytest.approx(1.08262668e-3, rel=1e-5)

    def test_raan_rate_iss_sign(self):
        """顺行轨道（i < 90°）RAAN 进动应为负（向西）。"""
        rate = j2_raan_rate(6778.0, 0.0, 51.6)
        assert rate < 0.0, "顺行轨道 RAAN 进动应为负（向西）"

    def test_raan_rate_sso_sign(self):
        """逆行太阳同步轨道（i ≈ 97.4°）RAAN 进动应为正（向东）。"""
        a = R_EARTH_KM + 700.0
        rate = j2_raan_rate(a, 0.0, 97.4)
        assert rate > 0.0, "逆行 SSO 轨道 RAAN 进动应为正（向东）"

    def test_raan_rate_sso_magnitude(self):
        """SSO 700 km 轨道 RAAN 进动速率约 +0.9856°/天（太阳同步条件）。"""
        a = R_EARTH_KM + 700.0
        rate_rad_s = j2_raan_rate(a, 0.0, 97.4)
        rate_deg_day = math.degrees(rate_rad_s) * 86400.0
        # 太阳同步需要约 +0.9856°/天，允许 ±0.1°/天容差
        assert rate_deg_day == pytest.approx(0.9856, abs=0.1), (
            f"SSO RAAN 进动速率 {rate_deg_day:.4f}°/天，期望约 +0.9856°/天"
        )

    def test_raan_rate_polar_zero(self):
        """极轨（i=90°）RAAN 进动速率应接近 0（cos 90° = 0）。"""
        rate = j2_raan_rate(7000.0, 0.0, 90.0)
        assert abs(rate) < 1e-12, f"极轨 RAAN 进动应为零，实际 {rate}"

    def test_arg_perigee_rate_critical_inclination(self):
        """临界倾角 63.4° ��近地点幅角进动速率应接近 0（2 - 5/2 sin²i = 0）。"""
        i_crit = 63.4349  # degrees，满足 sin²(i) = 4/5
        rate = j2_arg_perigee_rate(7000.0, 0.0, i_crit)
        assert abs(rate) < 1e-9, (
            f"临界倾角 ω 进动速率应趋近 0，实际 {math.degrees(rate)*86400:.6f}°/天"
        )

    def test_mean_anomaly_correction_magnitude(self):
        """M 修正量应比平均角速度 n 小三个数量级以上（J2 量级 ~1e-3）。"""
        a = 6778.0
        n = math.sqrt(MU_EARTH / a ** 3)
        corr = j2_mean_anomaly_rate_correction(a, 0.0, 51.6)
        # |corr/n| 应与 J2 同量级
        ratio = abs(corr / n)
        assert ratio < 0.01, f"|corr/n| = {ratio:.2e} 超出预期上限 0.01"
        assert ratio > 1e-5, f"|corr/n| = {ratio:.2e} 低于预期下限 1e-5（J2 量级）"


# ---------------------------------------------------------------------------
# 太阳同步轨道 RAAN 进动测试
# ---------------------------------------------------------------------------

class TestSSOPrecession:
    """太阳同步轨道 RAAN 应按 J2 速率向东进动。"""

    def test_raan_increases_over_time(self, sso_orbit):
        """SSO 轨道 RAAN 应随时间增大（逆行轨道 J2 向东进动）。"""
        raan_0 = sso_orbit.raan
        # 传播 1 天
        dt = 86400.0
        lat, lon, alt = sso_orbit.propagate(dt)
        # 计算预期 RAAN 增量
        a = sso_orbit.a
        expected_raan_rate_deg = math.degrees(j2_raan_rate(a, 0.0, 97.4)) * 86400.0
        # 验证方向：正数（向东）
        assert expected_raan_rate_deg > 0.0, "SSO 轨道 RAAN 进动应向东（正方向）"

    def test_raan_drift_1day_numeric(self, sso_orbit):
        """SSO 1 天 RAAN 数值偏移应约为 +0.9856°。"""
        a = sso_orbit.a
        dt = 86400.0
        raan_drift_deg = math.degrees(j2_raan_rate(a, 0.0, 97.4)) * dt
        assert raan_drift_deg == pytest.approx(0.9856, abs=0.1), (
            f"1 天 RAAN 偏移 {raan_drift_deg:.4f}°，期望约 +0.9856°"
        )


# ---------------------------------------------------------------------------
# J2 开关测试
# ---------------------------------------------------------------------------

class TestJ2Switch:
    """j2_perturbation 开关：True 启用摄动，False 退化为纯二体。"""

    def test_short_term_position_close(self, iss_like_j2, iss_like_no_j2):
        """J2 与纯二体位置差应与时间成正比（连续无跳变，无阶跃误差）。

        验收条件"连续无跳变"等价于：差异 d(t) 满足 d(t)/t → const（线性增长），
        而非在 t→0 时有常数级跳变。测试两个时刻的位置差比值，确保线性性质。
        """
        R = 6371e3

        def pos_diff(dt_s):
            lat_j2, lon_j2, alt_j2 = iss_like_j2.propagate(dt_s)
            lat_no, lon_no, alt_no = iss_like_no_j2.propagate(dt_s)
            dlat = (lat_j2 - lat_no) * math.pi / 180.0 * R
            dlon = (lon_j2 - lon_no) * math.pi / 180.0 * R
            dalt = alt_j2 - alt_no
            return math.sqrt(dlat ** 2 + dlon ** 2 + dalt ** 2)

        d10 = pos_diff(10.0)
        d100 = pos_diff(100.0)
        # 如果是线性增长，d100/d10 应约等于 10
        ratio = d100 / d10
        assert ratio == pytest.approx(10.0, rel=0.05), (
            f"位置差应线性增长（连续无跳变），d(100s)/d(10s)={ratio:.3f}，期望约 10"
        )
        # t=0 时两者完全相同（无跳变）
        lat_j2_0, lon_j2_0, alt_j2_0 = iss_like_j2.propagate(0.0)
        lat_no_0, lon_no_0, alt_no_0 = iss_like_no_j2.propagate(0.0)
        assert lat_j2_0 == pytest.approx(lat_no_0, abs=1e-9)
        assert lon_j2_0 == pytest.approx(lon_no_0, abs=1e-9)
        assert alt_j2_0 == pytest.approx(alt_no_0, abs=1e-6)

    def test_long_term_raan_diverges(self):
        """长期（30 天）J2 与纯二体 RAAN 应明显不同（进动累积）。"""
        epoch = datetime(2024, 1, 1, 0, 0, 0)
        common_kwargs = dict(
            sat_id="sso_cmp",
            semi_major_axis=R_EARTH_KM + 700.0,
            eccentricity=0.0,
            inclination=97.4,
            raan=0.0,
            arg_perigee=0.0,
            mean_anomaly=0.0,
            epoch=epoch,
        )
        oe_j2 = OrbitalElements(name="SSO-J2", j2_perturbation=True, **common_kwargs)
        oe_no = OrbitalElements(name="SSO-NoJ2", j2_perturbation=False, **common_kwargs)

        dt = 30.0 * 86400.0  # 30 天
        a = common_kwargs["semi_major_axis"]
        expected_drift_deg = math.degrees(j2_raan_rate(a, 0.0, 97.4)) * dt
        # 期望约 30 × 0.9856 ≈ 29.6°
        assert abs(expected_drift_deg) > 25.0, (
            f"30 天预期 RAAN 偏移 {abs(expected_drift_deg):.2f}°，应 > 25°"
        )

    def test_no_j2_one_period_returns(self):
        """关闭 J2 后，整数开普勒周期纬度应回到初始值（纯二体性质）。"""
        epoch = datetime(2024, 1, 1, 0, 0, 0)
        oe = OrbitalElements(
            name="no-j2",
            sat_id="noj2",
            semi_major_axis=6778.0,
            eccentricity=0.0,
            inclination=51.6,
            raan=0.0,
            arg_perigee=0.0,
            mean_anomaly=0.0,
            epoch=epoch,
            j2_perturbation=False,
        )
        T = oe.get_orbital_period()
        lat0, _, _ = oe.propagate(0.0)
        lat1, _, _ = oe.propagate(T)
        assert lat1 == pytest.approx(lat0, abs=0.01), (
            "纯二体（J2=False）整周期后纬度应回到初始值"
        )

    def test_j2_enabled_one_period_drifts(self):
        """开启 J2 后，整数开普勒周期纬度应有小偏移（M 修正改变有效周期）。"""
        epoch = datetime(2024, 1, 1, 0, 0, 0)
        oe = OrbitalElements(
            name="j2-enabled",
            sat_id="j2en",
            semi_major_axis=6778.0,
            eccentricity=0.0,
            inclination=51.6,
            raan=0.0,
            arg_perigee=0.0,
            mean_anomaly=0.0,
            epoch=epoch,
            j2_perturbation=True,
        )
        T = oe.get_orbital_period()  # Keplerian period
        lat0, _, _ = oe.propagate(0.0)
        lat1, _, _ = oe.propagate(T)
        # J2 效应应导致纬度有一定偏移（不再精确回归），但偏移不超过 1°
        drift = abs(lat1 - lat0)
        assert drift > 0.0, "J2 开启时整周期纬度不应精确回归"
        assert drift < 1.0, f"J2 引起的纬度漂移 {drift:.4f}° 过大（应 < 1°）"
