# -*- coding: utf-8 -*-
"""单元测试：速率计算函数的数值行为。

测试目标：
  - calculate_direct_rate       — 直连链路速率，含 Ka/X 天线基础速率差异与 RAW_IMAGE 0.6 折扣
  - calculate_relay_rate        — 单跳中继速率，min(rate1, rate2) 瓶颈逻辑与 RAW_IMAGE 折扣
  - calculate_inter_satellite_rate — GEO 星间链路速率，最小速率下限 100 Mbps
  - calculate_multi_hop_relay_rate — 多跳中继速率，min(rate1, rate2, rate3) 瓶颈逻辑

测试策略：
  - 单调性：速率随距离增大而单调下降。
  - 边界值：最小速率下限（direct/relay 为 5 Mbps；inter_satellite 为 100 Mbps）。
  - 折扣比例：RAW_IMAGE 触发 0.6 折扣（direct/relay）或 0.5 折扣（multi_hop_relay）。
  - Ka/X 天线：Ka 基础速率 200，X 为 100，相同条件下 Ka 速率约是 X 的两倍。
"""
import math

import pytest

from backend.orbit import (
    calculate_direct_rate,
    calculate_inter_satellite_rate,
    calculate_multi_hop_relay_rate,
    calculate_relay_rate,
)


# --------------------------------------------------------------------------- #
# 辅助夹具与工厂                                                              #
# --------------------------------------------------------------------------- #

def _make_sat(lat=0.0, lon=0.0, alt_m=500_000):
    """构造卫星位置字典（alt 单位：米）。"""
    return {"lat": lat, "lon": lon, "alt": alt_m}


def _make_gs(lat=0.0, lon=0.0, antenna_type="Ka"):
    """构造地面站字典。"""
    return {"lat": lat, "lon": lon, "antenna_type": antenna_type}


def _make_geo(lat=0.0, lon=0.0, alt_m=35_786_000):
    """构造 GEO 卫星位置字典（alt 单位：米）。"""
    return {"lat": lat, "lon": lon, "alt": alt_m}


# --------------------------------------------------------------------------- #
# calculate_direct_rate                                                        #
# --------------------------------------------------------------------------- #

class TestCalculateDirectRate:
    """direct_rate = base_rate * exp(-distance/10000)，下限 5 Mbps。"""

    def test_basic_ka_returns_positive(self):
        """Ka 天线卫星在近距离应返回正速率。"""
        sat = _make_sat(lat=10.0, lon=10.0, alt_m=500_000)
        gs = _make_gs(lat=10.0, lon=10.0, antenna_type="Ka")
        rate = calculate_direct_rate(sat, gs)
        assert rate > 0

    def test_basic_x_returns_positive(self):
        """X 天线卫星在近距离应返回正速率。"""
        sat = _make_sat(lat=10.0, lon=10.0, alt_m=500_000)
        gs = _make_gs(lat=10.0, lon=10.0, antenna_type="X")
        rate = calculate_direct_rate(sat, gs)
        assert rate > 0

    def test_ka_base_rate_twice_x(self):
        """相同位置下 Ka 基础速率 200 约是 X 基础速率 100 的两倍。"""
        sat = _make_sat(lat=5.0, lon=5.0, alt_m=600_000)
        gs_ka = _make_gs(lat=5.0, lon=5.0, antenna_type="Ka")
        gs_x = _make_gs(lat=5.0, lon=5.0, antenna_type="X")
        rate_ka = calculate_direct_rate(sat, gs_ka)
        rate_x = calculate_direct_rate(sat, gs_x)
        assert rate_ka == pytest.approx(rate_x * 2.0, rel=1e-9)

    def test_raw_image_discount_0_6(self):
        """RAW_IMAGE 数据类型速率应为非 RAW_IMAGE 的 0.6 倍（当未触及下限时）。"""
        sat = _make_sat(lat=20.0, lon=20.0, alt_m=500_000)
        gs = _make_gs(lat=20.0, lon=20.0, antenna_type="Ka")
        rate_normal = calculate_direct_rate(sat, gs, data_type="DATA_SLICE")
        rate_raw = calculate_direct_rate(sat, gs, data_type="RAW_IMAGE")
        # 只要 normal 速率远高于下限 5，折扣比例即为 0.6
        if rate_normal * 0.6 > 5:
            assert rate_raw == pytest.approx(rate_normal * 0.6, rel=1e-9)
        else:
            assert rate_raw >= 5.0

    def test_minimum_rate_floor_5(self):
        """极远距离下速率应不低于 5 Mbps（最小速率下限）。"""
        sat = _make_sat(lat=85.0, lon=0.0, alt_m=500_000)
        gs = _make_gs(lat=-85.0, lon=180.0, antenna_type="X")
        rate = calculate_direct_rate(sat, gs)
        assert rate >= 5.0

    def test_minimum_rate_raw_image_floor_5(self):
        """RAW_IMAGE 在极远距离下速率也不低于 5 Mbps。"""
        sat = _make_sat(lat=85.0, lon=0.0, alt_m=500_000)
        gs = _make_gs(lat=-85.0, lon=180.0, antenna_type="Ka")
        rate = calculate_direct_rate(sat, gs, data_type="RAW_IMAGE")
        assert rate >= 5.0

    def test_rate_decreases_as_distance_increases(self):
        """速率随距离（经度差）增大而单调下降或维持下限。"""
        gs = _make_gs(lat=0.0, lon=0.0, antenna_type="Ka")
        sat_near = _make_sat(lat=0.0, lon=5.0, alt_m=500_000)
        sat_mid = _make_sat(lat=0.0, lon=30.0, alt_m=500_000)
        sat_far = _make_sat(lat=0.0, lon=80.0, alt_m=500_000)
        rate_near = calculate_direct_rate(sat_near, gs)
        rate_mid = calculate_direct_rate(sat_mid, gs)
        rate_far = calculate_direct_rate(sat_far, gs)
        # 单调下降（允许触及下限后持平）
        assert rate_near >= rate_mid >= rate_far

    def test_rate_decreases_with_altitude(self):
        """卫星高度越高，到地面站距离越远，速率不高于低轨速率。"""
        gs = _make_gs(lat=0.0, lon=0.0, antenna_type="Ka")
        sat_low = _make_sat(lat=0.0, lon=0.0, alt_m=300_000)
        sat_high = _make_sat(lat=0.0, lon=0.0, alt_m=1_500_000)
        rate_low = calculate_direct_rate(sat_low, gs)
        rate_high = calculate_direct_rate(sat_high, gs)
        assert rate_low >= rate_high

    def test_none_data_type_treated_as_no_discount(self):
        """data_type=None 时不触发折扣，速率与非 RAW_IMAGE 类型一致。"""
        sat = _make_sat(lat=15.0, lon=15.0, alt_m=500_000)
        gs = _make_gs(lat=15.0, lon=15.0, antenna_type="Ka")
        rate_none = calculate_direct_rate(sat, gs, data_type=None)
        rate_slice = calculate_direct_rate(sat, gs, data_type="DATA_SLICE")
        # 两者均不触发折扣，结果相同
        assert rate_none == pytest.approx(rate_slice, rel=1e-9)


# --------------------------------------------------------------------------- #
# calculate_relay_rate                                                         #
# --------------------------------------------------------------------------- #

class TestCalculateRelayRate:
    """relay_rate = min(rate1, rate2)，下限 5 Mbps。"""

    def test_basic_relay_positive(self):
        """基本中继链路应返回正速率。"""
        sat = _make_sat(lat=0.0, lon=0.0, alt_m=500_000)
        geo = _make_geo(lat=0.0, lon=0.0)
        gs = _make_gs(lat=0.0, lon=10.0, antenna_type="Ka")
        rate = calculate_relay_rate(sat, geo, gs)
        assert rate > 0

    def test_minimum_rate_floor_5(self):
        """极端条件下中继速率不低于 5 Mbps。"""
        sat = _make_sat(lat=80.0, lon=0.0, alt_m=500_000)
        geo = _make_geo(lat=0.0, lon=180.0)
        gs = _make_gs(lat=-80.0, lon=90.0, antenna_type="X")
        rate = calculate_relay_rate(sat, geo, gs)
        assert rate >= 5.0

    def test_raw_image_discount_0_6(self):
        """RAW_IMAGE 中继速率应为非 RAW_IMAGE 的 0.6 倍（当未触及下限时）。"""
        sat = _make_sat(lat=0.0, lon=5.0, alt_m=500_000)
        geo = _make_geo(lat=0.0, lon=0.0)
        gs = _make_gs(lat=0.0, lon=-5.0, antenna_type="Ka")
        rate_normal = calculate_relay_rate(sat, geo, gs, data_type="DATA_SLICE")
        rate_raw = calculate_relay_rate(sat, geo, gs, data_type="RAW_IMAGE")
        if rate_normal * 0.6 > 5:
            assert rate_raw == pytest.approx(rate_normal * 0.6, rel=1e-9)
        else:
            assert rate_raw >= 5.0

    def test_bottleneck_is_min_of_two_legs(self):
        """中继速率受限于两段链路中较慢的一段（瓶颈逻辑）。"""
        # 通过分析：calculate_relay_rate 内部取 min(rate1, rate2)
        # rate1 由卫星→GEO 距离决定；rate2 由 GEO→地面站距离决定
        sat = _make_sat(lat=0.0, lon=0.0, alt_m=500_000)
        geo = _make_geo(lat=0.0, lon=0.0)
        # 地面站离 GEO 很远 → rate2 很小 → 成为瓶颈
        gs_far = _make_gs(lat=80.0, lon=80.0, antenna_type="Ka")
        gs_near = _make_gs(lat=0.0, lon=5.0, antenna_type="Ka")
        rate_far = calculate_relay_rate(sat, geo, gs_far)
        rate_near = calculate_relay_rate(sat, geo, gs_near)
        assert rate_near >= rate_far

    def test_rate_monotone_with_gs_distance(self):
        """地面站到 GEO 距离增大时，中继速率单调下降（或维持下限）。"""
        sat = _make_sat(lat=0.0, lon=0.0, alt_m=500_000)
        geo = _make_geo(lat=0.0, lon=0.0)
        rates = []
        for lon_offset in [5.0, 20.0, 50.0]:
            gs = _make_gs(lat=0.0, lon=lon_offset, antenna_type="Ka")
            rates.append(calculate_relay_rate(sat, geo, gs))
        assert rates[0] >= rates[1] >= rates[2]


# --------------------------------------------------------------------------- #
# calculate_inter_satellite_rate                                               #
# --------------------------------------------------------------------------- #

class TestCalculateInterSatelliteRate:
    """inter_satellite_rate = 2000 * exp(-dist/40000)，下限 100 Mbps。"""

    def test_same_position_near_max_rate(self):
        """两颗 GEO 卫星同经纬度时，距离最小，速率应接近上界 2000 Mbps。"""
        geo1 = _make_geo(lat=0.0, lon=0.0)
        geo2 = _make_geo(lat=0.0, lon=0.0)
        rate = calculate_inter_satellite_rate(geo1, geo2)
        assert rate == pytest.approx(2000.0, rel=0.01)

    def test_minimum_rate_floor_100(self):
        """极远距离 GEO 星间速率不低于 100 Mbps。"""
        geo1 = _make_geo(lat=0.0, lon=0.0)
        geo2 = _make_geo(lat=0.0, lon=180.0)
        rate = calculate_inter_satellite_rate(geo1, geo2)
        assert rate >= 100.0

    def test_rate_decreases_with_angular_separation(self):
        """GEO 星间经度差越大，速率越低（单调下降）。"""
        geo1 = _make_geo(lat=0.0, lon=0.0)
        geo_near = _make_geo(lat=0.0, lon=10.0)
        geo_mid = _make_geo(lat=0.0, lon=60.0)
        geo_far = _make_geo(lat=0.0, lon=150.0)
        rate_near = calculate_inter_satellite_rate(geo1, geo_near)
        rate_mid = calculate_inter_satellite_rate(geo1, geo_mid)
        rate_far = calculate_inter_satellite_rate(geo1, geo_far)
        assert rate_near >= rate_mid >= rate_far

    def test_symmetric(self):
        """星间链路速率应对称：rate(A→B) == rate(B→A)。"""
        geo1 = _make_geo(lat=10.0, lon=20.0)
        geo2 = _make_geo(lat=-10.0, lon=60.0)
        rate_ab = calculate_inter_satellite_rate(geo1, geo2)
        rate_ba = calculate_inter_satellite_rate(geo2, geo1)
        assert rate_ab == pytest.approx(rate_ba, rel=1e-9)

    def test_rate_always_positive(self):
        """任意两颗 GEO 卫星之间的速率应始终为正。"""
        positions = [
            _make_geo(lat=0.0, lon=0.0),
            _make_geo(lat=0.0, lon=90.0),
            _make_geo(lat=10.0, lon=45.0),
            _make_geo(lat=-20.0, lon=120.0),
        ]
        for i, g1 in enumerate(positions):
            for j, g2 in enumerate(positions):
                if i != j:
                    rate = calculate_inter_satellite_rate(g1, g2)
                    assert rate > 0, f"星间速率应为正，实际 rate={rate} for pair ({i},{j})"


# --------------------------------------------------------------------------- #
# calculate_multi_hop_relay_rate                                               #
# --------------------------------------------------------------------------- #

class TestCalculateMultiHopRelayRate:
    """multi_hop_relay_rate = min(rate1, rate2, rate3)，无全局下限（由各段决定）。"""

    def test_basic_multi_hop_positive(self):
        """标准配置下多跳中继应返回正速率。"""
        sat = _make_sat(lat=0.0, lon=0.0, alt_m=500_000)
        geo1 = _make_geo(lat=0.0, lon=5.0)
        geo2 = _make_geo(lat=0.0, lon=10.0)
        gs = _make_gs(lat=0.0, lon=15.0, antenna_type="Ka")
        rate = calculate_multi_hop_relay_rate(sat, geo1, geo2, gs)
        assert rate > 0

    def test_raw_image_discount_0_5(self):
        """RAW_IMAGE 多跳中继速率应为非 RAW_IMAGE 的 0.5 倍（当未触及下限时）。"""
        sat = _make_sat(lat=0.0, lon=0.0, alt_m=500_000)
        geo1 = _make_geo(lat=0.0, lon=5.0)
        geo2 = _make_geo(lat=0.0, lon=10.0)
        gs = _make_gs(lat=0.0, lon=15.0, antenna_type="Ka")
        rate_normal = calculate_multi_hop_relay_rate(sat, geo1, geo2, gs, data_type="DATA_SLICE")
        rate_raw = calculate_multi_hop_relay_rate(sat, geo1, geo2, gs, data_type="RAW_IMAGE")
        assert rate_raw == pytest.approx(rate_normal * 0.5, rel=1e-9)

    def test_bottleneck_three_legs(self):
        """多跳速率不超过任何单段的速率（三段瓶颈约束）。"""
        sat = _make_sat(lat=0.0, lon=0.0, alt_m=500_000)
        geo1 = _make_geo(lat=0.0, lon=5.0)
        geo2 = _make_geo(lat=0.0, lon=10.0)
        gs = _make_gs(lat=0.0, lon=15.0, antenna_type="Ka")
        rate_multihop = calculate_multi_hop_relay_rate(sat, geo1, geo2, gs)
        # 直接计算星间链路段速率作为对照
        rate_isl = calculate_inter_satellite_rate(geo1, geo2)
        # 多跳速率不超过星间段速率
        assert rate_multihop <= rate_isl + 1e-9  # 加小量容差避免浮点问题

    def test_rate_decreases_with_gs_distance(self):
        """地面站越远，多跳中继速率越低（单调性）。"""
        sat = _make_sat(lat=0.0, lon=0.0, alt_m=500_000)
        geo1 = _make_geo(lat=0.0, lon=5.0)
        geo2 = _make_geo(lat=0.0, lon=10.0)
        gs_near = _make_gs(lat=0.0, lon=15.0, antenna_type="Ka")
        gs_far = _make_gs(lat=0.0, lon=60.0, antenna_type="Ka")
        rate_near = calculate_multi_hop_relay_rate(sat, geo1, geo2, gs_near)
        rate_far = calculate_multi_hop_relay_rate(sat, geo1, geo2, gs_far)
        assert rate_near >= rate_far

    def test_none_data_type_no_discount(self):
        """data_type=None 时不触发折扣，速率与 DATA_SLICE 相同。"""
        sat = _make_sat(lat=5.0, lon=5.0, alt_m=500_000)
        geo1 = _make_geo(lat=0.0, lon=5.0)
        geo2 = _make_geo(lat=0.0, lon=10.0)
        gs = _make_gs(lat=0.0, lon=15.0, antenna_type="Ka")
        rate_none = calculate_multi_hop_relay_rate(sat, geo1, geo2, gs, data_type=None)
        rate_slice = calculate_multi_hop_relay_rate(sat, geo1, geo2, gs, data_type="DATA_SLICE")
        assert rate_none == pytest.approx(rate_slice, rel=1e-9)


# --------------------------------------------------------------------------- #
# _estimate_transmission_time（通过 SimulationEngine 访问）                    #
# --------------------------------------------------------------------------- #

class TestEstimateTransmissionTime:
    """_estimate_transmission_time：(size_mb * 8) / rate_mbps，rate<=0 返回 inf。"""

    @pytest.fixture(autouse=True)
    def engine(self):
        from backend.core import create_engine
        self.eng = create_engine(seed=0, autostart=False)
        yield
        self.eng.running = False

    def test_normal_transmission_time(self):
        """正常速率下传输时间 = size_mb * 8 / rate_mbps。"""
        t = self.eng._estimate_transmission_time(100.0, 200.0)
        expected = 100.0 * 8 / 200.0
        assert t == pytest.approx(expected, rel=1e-9)

    def test_zero_rate_returns_inf(self):
        """速率为 0 时应返回 inf（除零保护）。"""
        t = self.eng._estimate_transmission_time(100.0, 0.0)
        assert t == float("inf")

    def test_negative_rate_returns_inf(self):
        """速率为负数时应返回 inf（防御性边界）。"""
        t = self.eng._estimate_transmission_time(100.0, -10.0)
        assert t == float("inf")

    def test_large_data_large_time(self):
        """更大的数据量应对应更长的传输时间（线性正比）。"""
        rate = 50.0
        t_small = self.eng._estimate_transmission_time(10.0, rate)
        t_large = self.eng._estimate_transmission_time(100.0, rate)
        assert t_large == pytest.approx(t_small * 10.0, rel=1e-9)

    def test_higher_rate_shorter_time(self):
        """速率越高，传输时间越短。"""
        size = 500.0
        t_slow = self.eng._estimate_transmission_time(size, 10.0)
        t_fast = self.eng._estimate_transmission_time(size, 1000.0)
        assert t_fast < t_slow

    def test_unit_consistency(self):
        """1 MB 数据 @ 8 Mbps = 1 秒（单位一致性验证）。"""
        t = self.eng._estimate_transmission_time(1.0, 8.0)
        assert t == pytest.approx(1.0, rel=1e-9)
