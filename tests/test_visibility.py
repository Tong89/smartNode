# -*- coding: utf-8 -*-
"""单元测试：calc_central_angle / check_visibility / check_geo_visibility。

测试目标：
  - calc_central_angle   — 球面大圆地心角（度）
  - check_visibility     — 卫星-地面站仰角可见性（含 d<0.001 正上方边界）
  - check_geo_visibility — LEO-GEO 中继可见性（< 80° 阈值）

测试策略：
  - 使用已知几何值（同点=0°、对跖=180°、直角=90°）建立精确断言。
  - 覆盖仰角阈值边界（刚好高于/低于 10°）和正上方（d<0.001 特殊分支）。
  - 覆盖 GEO 可见角 80° 临界（79° 可见 / 81° 不可见）。
  - 从 tests/golden/orbital_baseline.json 读取黄金基准交叉验证。
"""
import json
import math
import os

import pytest

from backend.orbit import calc_central_angle, check_visibility, check_geo_visibility

# --------------------------------------------------------------------------- #
# 辅助：加载黄金基准                                                          #
# --------------------------------------------------------------------------- #
_GOLDEN_PATH = os.path.join(os.path.dirname(__file__), "golden", "orbital_baseline.json")


@pytest.fixture(scope="module")
def golden():
    with open(_GOLDEN_PATH, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# calc_central_angle                                                           #
# --------------------------------------------------------------------------- #
class TestCalcCentralAngle:
    """Haversine 公式的基本性质与已知数值验证。"""

    def test_same_point_is_zero(self):
        """同一点，地心角 = 0°。"""
        assert calc_central_angle(0, 0, 0, 0) == pytest.approx(0.0, abs=1e-9)

    def test_same_point_arbitrary_coords(self):
        """任意坐标的同一点，结果仍为 0°。"""
        assert calc_central_angle(45.5, -73.6, 45.5, -73.6) == pytest.approx(0.0, abs=1e-9)

    def test_antipodal_equator(self):
        """对跖点（赤道 0° 与 180°），地心角 = 180°。"""
        assert calc_central_angle(0, 0, 0, 180) == pytest.approx(180.0, abs=1e-6)

    def test_north_to_south_pole(self):
        """南北极对跖，地心角 = 180°。"""
        assert calc_central_angle(90, 0, -90, 0) == pytest.approx(180.0, abs=1e-6)

    def test_quarter_equator(self):
        """赤道相差 90° 经度，地心角 = 90°。"""
        assert calc_central_angle(0, 0, 0, 90) == pytest.approx(90.0, abs=1e-6)

    def test_equator_45_degrees(self):
        """赤道相差 45° 经度，地心角 = 45°。"""
        assert calc_central_angle(0, 0, 0, 45) == pytest.approx(45.0, abs=1e-6)

    def test_symmetry(self):
        """对称性：calc_central_angle(a, b, c, d) == calc_central_angle(c, d, a, b)。"""
        angle_ab = calc_central_angle(35.0, 139.0, 51.5, -0.1)
        angle_ba = calc_central_angle(51.5, -0.1, 35.0, 139.0)
        assert angle_ab == pytest.approx(angle_ba, abs=1e-9)

    def test_non_negative(self):
        """地心角始终 >= 0。"""
        cases = [
            (0, 0, 0, 0),
            (0, 0, 0, 90),
            (-90, 45, 90, -45),
            (35, 139, -34, 150),
        ]
        for lat1, lon1, lat2, lon2 in cases:
            angle = calc_central_angle(lat1, lon1, lat2, lon2)
            assert angle >= 0.0, f"角度不应为负，实际值={angle}"

    def test_max_is_180(self):
        """地心角最大值 = 180°（对跖点）。"""
        angle = calc_central_angle(90, 0, -90, 0)
        assert angle <= 180.0 + 1e-9

    def test_golden_diagonal(self, golden):
        """(45,45) 到 (-45,-45) 的黄金基准 ≈ 120°。"""
        ref = golden["calc_central_angle"]["diagonal_45_to_neg45"]
        result = calc_central_angle(*ref["inputs"])
        assert result == pytest.approx(ref["expected"], abs=ref["tol"])

    @pytest.mark.parametrize("case_key", [
        "same_point",
        "antipodal_equator",
        "quarter_equator",
        "north_to_south_pole",
        "equator_45deg",
    ])
    def test_golden_parametrized(self, golden, case_key):
        """批量验证黄金基准中的所有预设场景。"""
        ref = golden["calc_central_angle"][case_key]
        result = calc_central_angle(*ref["inputs"])
        assert result == pytest.approx(ref["expected"], abs=ref["tol"]), (
            f"{case_key}: 期望 {ref['expected']}°，实际 {result}°"
        )


# --------------------------------------------------------------------------- #
# check_visibility                                                              #
# --------------------------------------------------------------------------- #
class TestCheckVisibility:
    """仰角可见性计算：包含正上方边界、阈值边界与常规场景。"""

    # --- 正上方边界（d < 0.001 特殊分支） ---

    def test_overhead_visible_min_el_0(self):
        """卫星正上方：d < 0.001，仰角 = 90°，任何 min_elevation 阈值均可见。"""
        sat = {"lat": 35.0, "lon": 139.0, "alt": 500000}
        gs = {"lat": 35.0, "lon": 139.0}
        assert check_visibility(sat, gs, min_elevation=0) is True

    def test_overhead_visible_min_el_10(self):
        """正上方仰角 = 90°，10° 阈值也应可见。"""
        sat = {"lat": 35.0, "lon": 139.0, "alt": 500000}
        gs = {"lat": 35.0, "lon": 139.0}
        assert check_visibility(sat, gs, min_elevation=10) is True

    def test_overhead_visible_min_el_90(self):
        """正上方仰角 = 90°，90° 阈值也应可见（临界等号）。"""
        sat = {"lat": 35.0, "lon": 139.0, "alt": 500000}
        gs = {"lat": 35.0, "lon": 139.0}
        assert check_visibility(sat, gs, min_elevation=90) is True

    def test_overhead_different_altitude(self):
        """不同高度的正上方卫星，均应可见（仰角 = 90°）。"""
        gs = {"lat": 51.5, "lon": -0.1}
        for alt_m in [300000, 550000, 1000000, 35786000]:
            sat = {"lat": 51.5, "lon": -0.1, "alt": alt_m}
            assert check_visibility(sat, gs, min_elevation=10) is True, (
                f"高度 {alt_m} m 的正上方卫星不应不可见"
            )

    # --- 仰角阈值边界 ---

    def test_small_angle_below_threshold(self):
        """地心角约 0.5°（仰角约 6.3°）< 10°，不可见。"""
        sat = {"lat": 35.5, "lon": 139.0, "alt": 500000}
        gs = {"lat": 35.0, "lon": 139.0}
        assert check_visibility(sat, gs, min_elevation=10) is False

    def test_moderate_angle_above_threshold(self):
        """地心角约 1°（仰角约 12.5°）> 10°，可见。"""
        sat = {"lat": 36.0, "lon": 139.0, "alt": 500000}
        gs = {"lat": 35.0, "lon": 139.0}
        assert check_visibility(sat, gs, min_elevation=10) is True

    def test_large_angle_below_threshold(self):
        """地心角约 60°（仰角约 3.7°）< 10°，不可见。"""
        sat = {"lat": 95.0, "lon": 139.0, "alt": 500000}
        gs = {"lat": 35.0, "lon": 139.0}
        assert check_visibility(sat, gs, min_elevation=10) is False

    def test_min_elevation_zero_always_passes_for_near_sat(self):
        """min_elevation=0 时，较近距离的卫星始终可见。"""
        sat = {"lat": 36.0, "lon": 139.0, "alt": 500000}
        gs = {"lat": 35.0, "lon": 139.0}
        assert check_visibility(sat, gs, min_elevation=0) is True

    # --- 仰角单调性 ---

    def test_visibility_monotone_with_elevation_threshold(self):
        """对同一卫星-地面站对，随 min_elevation 增大，可见性不会从 False 变回 True。"""
        sat = {"lat": 37.0, "lon": 139.0, "alt": 500000}
        gs = {"lat": 35.0, "lon": 139.0}
        thresholds = list(range(0, 91, 5))
        results = [check_visibility(sat, gs, min_elevation=e) for e in thresholds]
        # 一旦变为 False，后续不能再变 True
        flipped = False
        for r in results:
            if flipped:
                assert r is False, "min_elevation 增大后可见性不应从 False 变回 True"
            if r is False:
                flipped = True

    # --- 极地地面站场景 ---

    def test_polar_ground_station_overhead(self):
        """极地地面站（南极）正上方卫星，应可见。"""
        sat = {"lat": -90.0, "lon": 0.0, "alt": 400000}
        gs = {"lat": -90.0, "lon": 0.0}
        assert check_visibility(sat, gs, min_elevation=10) is True

    # --- 黄金基准交叉验证 ---

    def test_golden_overhead_min_el_0(self, golden):
        ref = golden["check_visibility"]["overhead_min_el_0"]
        sat = {"lat": ref["sat_lat"], "lon": ref["sat_lon"], "alt": ref["sat_alt_m"]}
        gs = {"lat": ref["gs_lat"], "lon": ref["gs_lon"]}
        assert check_visibility(sat, gs, min_elevation=ref["min_elevation"]) is ref["expected"]

    def test_golden_overhead_min_el_90(self, golden):
        ref = golden["check_visibility"]["overhead_min_el_90"]
        sat = {"lat": ref["sat_lat"], "lon": ref["sat_lon"], "alt": ref["sat_alt_m"]}
        gs = {"lat": ref["gs_lat"], "lon": ref["gs_lon"]}
        assert check_visibility(sat, gs, min_elevation=ref["min_elevation"]) is ref["expected"]

    def test_golden_small_angle_below_threshold(self, golden):
        ref = golden["check_visibility"]["small_angle_below_threshold"]
        sat = {"lat": ref["sat_lat"], "lon": ref["sat_lon"], "alt": ref["sat_alt_m"]}
        gs = {"lat": ref["gs_lat"], "lon": ref["gs_lon"]}
        assert check_visibility(sat, gs, min_elevation=ref["min_elevation"]) is ref["expected"]

    def test_golden_moderate_angle_visible(self, golden):
        ref = golden["check_visibility"]["moderate_angle_visible"]
        sat = {"lat": ref["sat_lat"], "lon": ref["sat_lon"], "alt": ref["sat_alt_m"]}
        gs = {"lat": ref["gs_lat"], "lon": ref["gs_lon"]}
        assert check_visibility(sat, gs, min_elevation=ref["min_elevation"]) is ref["expected"]

    def test_golden_large_angle_below_threshold(self, golden):
        ref = golden["check_visibility"]["large_angle_below_threshold"]
        sat = {"lat": ref["sat_lat"], "lon": ref["sat_lon"], "alt": ref["sat_alt_m"]}
        gs = {"lat": ref["gs_lat"], "lon": ref["gs_lon"]}
        assert check_visibility(sat, gs, min_elevation=ref["min_elevation"]) is ref["expected"]


# --------------------------------------------------------------------------- #
# check_geo_visibility                                                          #
# --------------------------------------------------------------------------- #
class TestCheckGeoVisibility:
    """LEO-GEO 中继可见性：angle < 80° 阈值的各边界场景。"""

    def test_same_position_visible(self):
        """LEO 与 GEO 在同一经纬度，角度 = 0°，应可见。"""
        leo = {"lat": 0.0, "lon": 0.0, "alt": 500000}
        geo = {"lat": 0.0, "lon": 0.0, "alt": 35786000}
        assert check_geo_visibility(leo, geo) is True

    def test_angle_79_visible(self):
        """赤道上地心角 = 79° < 80°，应可见。"""
        leo = {"lat": 0.0, "lon": 0.0, "alt": 500000}
        geo = {"lat": 0.0, "lon": 79.0, "alt": 35786000}
        assert check_geo_visibility(leo, geo) is True

    def test_angle_81_not_visible(self):
        """赤道上地心角 = 81° > 80°，不应可见。"""
        leo = {"lat": 0.0, "lon": 0.0, "alt": 500000}
        geo = {"lat": 0.0, "lon": 81.0, "alt": 35786000}
        assert check_geo_visibility(leo, geo) is False

    def test_angle_90_not_visible(self):
        """赤道上地心角 = 90° 远超 80°，不可见。"""
        leo = {"lat": 0.0, "lon": 0.0, "alt": 500000}
        geo = {"lat": 0.0, "lon": 90.0, "alt": 35786000}
        assert check_geo_visibility(leo, geo) is False

    def test_antipodal_not_visible(self):
        """对跖点（角度 = 180°），不可见。"""
        leo = {"lat": 0.0, "lon": 0.0, "alt": 500000}
        geo = {"lat": 0.0, "lon": 180.0, "alt": 35786000}
        assert check_geo_visibility(leo, geo) is False

    def test_altitude_does_not_affect_result(self):
        """check_geo_visibility 仅依赖地心角（纬经度），高度字段不影响结果。"""
        leo_low = {"lat": 0.0, "lon": 0.0, "alt": 300000}
        leo_high = {"lat": 0.0, "lon": 0.0, "alt": 1200000}
        geo = {"lat": 0.0, "lon": 50.0, "alt": 35786000}
        assert check_geo_visibility(leo_low, geo) == check_geo_visibility(leo_high, geo)

    def test_polar_leo_equatorial_geo(self):
        """极地 LEO（±60°）与赤道 GEO 的可见性。"""
        geo = {"lat": 0.0, "lon": 0.0, "alt": 35786000}
        leo_60 = {"lat": 60.0, "lon": 0.0, "alt": 500000}
        # 角度 = 60° < 80°，应可见
        assert check_geo_visibility(leo_60, geo) is True
        leo_85 = {"lat": 85.0, "lon": 0.0, "alt": 500000}
        # 角度 = 85° > 80°，不可见
        assert check_geo_visibility(leo_85, geo) is False

    # --- 黄金基准交叉验证 ---

    @pytest.mark.parametrize("case_key", [
        "same_position",
        "angle_79_visible",
        "angle_81_not_visible",
        "angle_90_not_visible",
    ])
    def test_golden_geo_visibility(self, golden, case_key):
        """批量验证黄金基准中的所有 GEO 可见性场景。"""
        ref = golden["check_geo_visibility"][case_key]
        leo = {"lat": ref["leo_lat"], "lon": ref["leo_lon"], "alt": ref["leo_alt_m"]}
        geo = {"lat": ref["geo_lat"], "lon": ref["geo_lon"], "alt": ref["geo_alt_m"]}
        result = check_geo_visibility(leo, geo)
        assert result is ref["expected"], (
            f"{case_key}: 期望 {ref['expected']}，实际 {result}（说明：{ref['note']}）"
        )


# --------------------------------------------------------------------------- #
# 综合场景：calc_central_angle 与 check_visibility 联动                       #
# --------------------------------------------------------------------------- #
class TestIntegrationCentralAngleVisibility:
    """通过已知地心角推算期望的 check_visibility 结果，验证两函数数值一致。"""

    def test_equatorial_satellite_500km_various_angles(self):
        """赤道上 500 km 高度卫星，对不同地心角的可见性批量断言。"""
        gs = {"lat": 0.0, "lon": 0.0}
        alt_m = 500000
        # 对于 500 km 高度，临界仰角 10° 对应的地心角约 55°
        # 小角度（< ~0.7°）仰角 < 10° → 不可见；中等角度（~1° ≤ x ≤ ~55°）→ 可见
        expected = [
            (0.5, False),    # 仰角约 6.3°
            (1.0, True),     # 仰角约 12.5°
            (10.0, True),    # 仰角约 61.7°
            (30.0, True),    # 仰角约 53.0°
            (45.0, True),    # 仰角约 27.7°
            (60.0, False),   # 仰角约 3.7°
        ]
        for angle_deg, exp_vis in expected:
            sat = {"lat": angle_deg, "lon": 0.0, "alt": alt_m}
            central = calc_central_angle(sat["lat"], sat["lon"], gs["lat"], gs["lon"])
            vis = check_visibility(sat, gs, min_elevation=10)
            assert vis is exp_vis, (
                f"地心角 {central:.2f}° (偏移 {angle_deg}°)：期望可见={exp_vis}，实际={vis}"
            )
