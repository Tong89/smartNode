# -*- coding: utf-8 -*-
"""性能基准回归看门狗 — pytest-benchmark

对核心算法建立基准，并通过 --benchmark-compare 与历史基线对比，
超出阈值时 CI 标记失败（回归看门狗）。

覆盖范围：
  1. orbit.propagate          — 二体轨道推进（Kepler 方程迭代）
  2. orbit.check_visibility   — 卫星–地面站仰角可见性计算
  3. orbit.calculate_direct_rate   — 直连链路速率
  4. orbit.calculate_relay_rate    — 单跳中继链路速率
  5. orbit.calculate_multi_hop_relay_rate — 多跳中继链路速率
  6. engine._update_resource_utilization  — 资源利用率聚合
  7. engine._update_transmissions         — 传输状态推进（dt=1s）
  8. calc_central_angle × 1000           — 大圆地心角批量计算
  9. scheduling: find_best_available_link — 链路决策（空引擎单次）

所有基准均使用固定种子以保证可复现性。
基线存储在 .benchmarks/ 目录（由 pytest-benchmark 管理）。

CI 中与基线对比：
  pytest tests/test_perf_benchmarks.py \
         --benchmark-compare \
         --benchmark-compare-fail=mean:20% \
         --benchmark-storage=.benchmarks/

本地首次运行（建立基线）：
  pytest tests/test_perf_benchmarks.py --benchmark-save=baseline
"""
import math
import random

import pytest

from backend.orbit import (
    OrbitalElements,
    calc_central_angle,
    calculate_direct_rate,
    calculate_inter_satellite_rate,
    calculate_multi_hop_relay_rate,
    calculate_relay_rate,
    check_visibility,
)
from backend.core import create_engine, TransmissionRequest


# --------------------------------------------------------------------------- #
# 共享测试夹具                                                                #
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def leo_element():
    """固定轨道根数的 LEO 卫星 OrbitalElements 实例（模块作用域）。"""
    return OrbitalElements(
        name="BENCH-LEO",
        sat_id="bench-leo-1",
        semi_major_axis=6921.0,   # 550 km 轨道
        eccentricity=0.001,
        inclination=53.0,
        raan=20.0,
        arg_perigee=45.0,
        mean_anomaly=0.0,
    )


@pytest.fixture(scope="module")
def bench_sat_pos():
    """固定卫星位置（lat/lon/alt）。"""
    return {"lat": 45.0, "lon": 120.0, "alt": 550_000}  # alt in metres


@pytest.fixture(scope="module")
def bench_gs_ka():
    """Ka 天线地面站。"""
    return {"lat": 39.9, "lon": 116.4, "antenna_type": "Ka"}


@pytest.fixture(scope="module")
def bench_gs_x():
    """X 天线地面站。"""
    return {"lat": 31.2, "lon": 121.5, "antenna_type": "X"}


@pytest.fixture(scope="module")
def bench_geo_pos():
    """固定 GEO 中继星位置。"""
    return {"lat": 0.0, "lon": 105.0, "alt": 35_786_000}


@pytest.fixture(scope="module")
def bench_geo2_pos():
    """第二个 GEO 中继星位置（多跳链路使用）。"""
    return {"lat": 0.0, "lon": 75.0, "alt": 35_786_000}


@pytest.fixture(scope="module")
def bench_engine():
    """不启动后台线程的固定种子引擎，模块作用域，避免重复初始化开销。"""
    return create_engine(seed=42, autostart=False)


# --------------------------------------------------------------------------- #
# 1. OrbitalElements.propagate                                                #
# --------------------------------------------------------------------------- #

class TestPropagatePerf:
    """轨道推进函数性能基准。"""

    def test_propagate_single(self, benchmark, leo_element):
        """单次轨道推进（t=0 起点）。"""
        result = benchmark(leo_element.propagate, 0.0)
        lat, lon, alt = result
        assert -90 <= lat <= 90
        assert -180 <= lon <= 180
        assert alt > 0

    def test_propagate_at_one_orbit(self, benchmark, leo_element):
        """推进至近一整圈（轨道周期 ≈ 5700s）。"""
        period = leo_element.get_orbital_period()
        result = benchmark(leo_element.propagate, period)
        lat, lon, alt = result
        assert -90 <= lat <= 90

    def test_propagate_large_t(self, benchmark, leo_element):
        """推进至大时间值（86400s = 1天），测试模运算稳定性。"""
        result = benchmark(leo_element.propagate, 86400.0)
        lat, lon, alt = result
        assert -90 <= lat <= 90


# --------------------------------------------------------------------------- #
# 2. check_visibility                                                          #
# --------------------------------------------------------------------------- #

class TestVisibilityPerf:
    """可见性检查性能基准。"""

    def test_visibility_above_horizon(self, benchmark, bench_sat_pos, bench_gs_ka):
        """仰角计算 — 卫星在地平线以上的典型情形。"""
        result = benchmark(check_visibility, bench_sat_pos, bench_gs_ka, 10)
        assert isinstance(result, bool)

    def test_visibility_near_horizon(self, benchmark):
        """仰角计算 — 接近地平线（大地心角）的边界情形。"""
        sat = {"lat": 80.0, "lon": 0.0, "alt": 550_000}
        gs = {"lat": 0.0, "lon": 0.0, "antenna_type": "Ka"}
        result = benchmark(check_visibility, sat, gs, 5)
        assert isinstance(result, bool)


# --------------------------------------------------------------------------- #
# 3. calculate_direct_rate                                                     #
# --------------------------------------------------------------------------- #

class TestDirectRatePerf:
    """直连链路速率计算性能基准。"""

    def test_direct_rate_ka(self, benchmark, bench_sat_pos, bench_gs_ka):
        """Ka 天线直连速率。"""
        rate = benchmark(calculate_direct_rate, bench_sat_pos, bench_gs_ka)
        assert rate >= 5.0

    def test_direct_rate_x(self, benchmark, bench_sat_pos, bench_gs_x):
        """X 天线直连速率。"""
        rate = benchmark(calculate_direct_rate, bench_sat_pos, bench_gs_x)
        assert rate >= 5.0

    def test_direct_rate_raw_image_discount(self, benchmark, bench_sat_pos, bench_gs_ka):
        """RAW_IMAGE 0.6 折扣下的直连速率。"""
        rate = benchmark(calculate_direct_rate, bench_sat_pos, bench_gs_ka, "RAW_IMAGE")
        assert rate >= 5.0


# --------------------------------------------------------------------------- #
# 4. calculate_relay_rate                                                      #
# --------------------------------------------------------------------------- #

class TestRelayRatePerf:
    """单跳中继链路速率计算性能基准。"""

    def test_relay_rate_nominal(self, benchmark, bench_sat_pos, bench_geo_pos, bench_gs_ka):
        """正常参数下的单跳中继速率。"""
        rate = benchmark(calculate_relay_rate, bench_sat_pos, bench_geo_pos, bench_gs_ka)
        assert rate >= 5.0

    def test_relay_rate_raw_image(self, benchmark, bench_sat_pos, bench_geo_pos, bench_gs_ka):
        """RAW_IMAGE 下的单跳中继速率。"""
        rate = benchmark(calculate_relay_rate, bench_sat_pos, bench_geo_pos, bench_gs_ka, "RAW_IMAGE")
        assert rate >= 5.0


# --------------------------------------------------------------------------- #
# 5. calculate_multi_hop_relay_rate                                            #
# --------------------------------------------------------------------------- #

class TestMultiHopRatePerf:
    """多跳中继链路速率计算性能基准。"""

    def test_multi_hop_nominal(
        self, benchmark, bench_sat_pos, bench_geo_pos, bench_geo2_pos, bench_gs_ka
    ):
        """正常参数下的多跳速率。"""
        rate = benchmark(
            calculate_multi_hop_relay_rate,
            bench_sat_pos, bench_geo_pos, bench_geo2_pos, bench_gs_ka,
        )
        # multi_hop 无最低速率下限，但应为正数
        assert rate > 0

    def test_multi_hop_raw_image(
        self, benchmark, bench_sat_pos, bench_geo_pos, bench_geo2_pos, bench_gs_ka
    ):
        """RAW_IMAGE 0.5 折扣下的多跳速率。"""
        rate = benchmark(
            calculate_multi_hop_relay_rate,
            bench_sat_pos, bench_geo_pos, bench_geo2_pos, bench_gs_ka, "RAW_IMAGE",
        )
        assert rate > 0


# --------------------------------------------------------------------------- #
# 6. calc_central_angle 批量                                                   #
# --------------------------------------------------------------------------- #

class TestCentralAngleBatchPerf:
    """大圆地心角批量计算性能基准（模拟星座覆盖评估）。"""

    def _batch_calc(self, n: int = 1000):
        """对 n 个随机点对计算大圆地心角。"""
        rng = random.Random(0)
        total = 0.0
        for _ in range(n):
            lat1 = rng.uniform(-90, 90)
            lon1 = rng.uniform(-180, 180)
            lat2 = rng.uniform(-90, 90)
            lon2 = rng.uniform(-180, 180)
            total += calc_central_angle(lat1, lon1, lat2, lon2)
        return total

    def test_batch_1000(self, benchmark):
        """1000 次地心角计算的吞吐量。"""
        result = benchmark(self._batch_calc, 1000)
        assert result >= 0  # 所有角度之和为非负

    def test_batch_antipodal(self, benchmark):
        """对跖点（最大地心角 180°）边界情形。"""
        def antipodal():
            return calc_central_angle(0, 0, 0, 180)
        result = benchmark(antipodal)
        assert abs(result - 180.0) < 0.01

    def test_batch_same_point(self, benchmark):
        """同一点（地心角应为 0）边界情形。"""
        def same_point():
            return calc_central_angle(45.0, 120.0, 45.0, 120.0)
        result = benchmark(same_point)
        assert result < 0.001


# --------------------------------------------------------------------------- #
# 7. engine._update_resource_utilization                                       #
# --------------------------------------------------------------------------- #

class TestResourceUtilizationPerf:
    """资源利用率聚合计算性能基准。"""

    def test_update_resource_utilization(self, benchmark, bench_engine):
        """空引擎状态下的资源利用率更新。"""
        benchmark(bench_engine._update_resource_utilization)
        # 只要不抛出异常、返回值结构合法即可
        util = bench_engine.stats["resource_utilization"]
        assert "satellites" in util
        assert "ground_stations" in util
        assert "geo_relays" in util

    def test_update_resource_utilization_with_accepted_requests(self, benchmark):
        """有已接受请求时的资源利用率更新。"""
        eng = create_engine(seed=7, autostart=False)
        # 注入几条已接受请求以产生非零利用率
        for i in range(3):
            req = TransmissionRequest(
                data_type="DATA_SLICE",
                data_size=50,
                priority=5,
                max_delay=600,
                satellite_id=eng.leo_satellites[0].sat_id if eng.leo_satellites else "LEO-0",
            )
            req.status = "transmitting"
            eng.transmission_requests.append(req)
        benchmark(eng._update_resource_utilization)


# --------------------------------------------------------------------------- #
# 8. engine._update_transmissions                                              #
# --------------------------------------------------------------------------- #

class TestUpdateTransmissionsPerf:
    """传输状态推进性能基准。"""

    def test_update_transmissions_empty(self, benchmark, bench_engine):
        """无活跃传输时的推进（最快路径）。"""
        benchmark(bench_engine._update_transmissions, 1.0)

    def test_update_transmissions_delta_variants(self, benchmark):
        """不同 delta_time 值下的推进（dt=0.5 / 1.0 / 5.0）。"""
        eng = create_engine(seed=13, autostart=False)

        def run_all():
            for dt in (0.5, 1.0, 5.0):
                eng._update_transmissions(dt)

        benchmark(run_all)


# --------------------------------------------------------------------------- #
# 9. 端到端：simulate N 步                                                    #
# --------------------------------------------------------------------------- #

class TestSimulationStepPerf:
    """引擎多步仿真性能基准（无线程）。"""

    def test_ten_simulation_steps(self, benchmark):
        """在无后台线程的条件下手动推进 10 步（dt=1s 每步）。"""
        eng = create_engine(seed=99, autostart=False)

        def run_steps():
            for _ in range(10):
                eng.current_time += 1.0
                eng._update_resource_utilization()
                eng._update_transmissions(1.0)

        benchmark(run_steps)

    def test_propagate_all_satellites(self, benchmark):
        """对引擎中所有 LEO 卫星同时进行轨道推进（评估星座规模开销）。"""
        eng = create_engine(seed=0, autostart=False)

        def propagate_all():
            for sat in eng.leo_satellites:
                eng.get_satellite_position(sat, current_time=eng.current_time)

        benchmark(propagate_all)
