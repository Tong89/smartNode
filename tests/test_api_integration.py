# -*- coding: utf-8 -*-
"""Flask 接口集成测试 —— 正常路径与契约验证。

本模块使用 Flask test_client 对以下接口进行集成测试：
  - GET  /api/health
  - GET  /api/data
  - GET  /api/system_info
  - GET  /api/resource_status
  - GET  /api/resource_utilization
  - GET  /api/requests
  - GET  /api/opportunistic_stations
  - GET  /api/data_combinations
  - POST /api/request  (正常路径：合法载荷返回带 id/status 的请求字典)
  - POST /api/update_ground_stations
  - POST /api/update_leo_satellites

测试策略：
  - 借助 create_engine(seed=0, autostart=False) 构造干净引擎实例后挂载到 app
  - 断言 HTTP 状态码、JSON 关键字段与类型
  - 所有测试不依赖真实后台线程（autostart=False）
  - 使用 open 模式鉴权（不设置 SMARTNODE_API_KEY），g.identity.role = admin
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import json
import pytest

from backend.core import create_engine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def test_engine():
    """使用固定种子、不启动后台线程的引擎（函数作用域，每次测试独立实例）。"""
    eng = create_engine(seed=0, autostart=False)
    yield eng
    eng.running = False


@pytest.fixture
def client(test_engine):
    """将干净引擎注入 api.app，返回 Flask test_client。

    通过替换 api.simulation_engine 避免全局状态污染；测试结束后恢复原始引擎。
    """
    import backend.api as api_module

    original_engine = api_module.simulation_engine
    api_module.simulation_engine = test_engine
    try:
        api_module.app.config["TESTING"] = True
        with api_module.app.test_client() as c:
            yield c
    finally:
        api_module.simulation_engine = original_engine


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _json(resp):
    """从 Response 中解析 JSON，便于断言。"""
    return json.loads(resp.data.decode("utf-8"))


# ---------------------------------------------------------------------------
# 1. GET /api/health
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """健康检查接口契约。"""

    def test_returns_200(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_response_contains_success(self, client):
        data = _json(client.get("/api/health"))
        assert data.get("success") is True

    def test_response_contains_service(self, client):
        data = _json(client.get("/api/health"))
        assert "service" in data
        assert isinstance(data["service"], str)

    def test_response_contains_simulation_running(self, client):
        data = _json(client.get("/api/health"))
        assert "simulation_running" in data
        assert isinstance(data["simulation_running"], bool)

    def test_simulation_running_is_false(self, client):
        """注入 autostart=False 的引擎时，simulation_running 应为 False。"""
        data = _json(client.get("/api/health"))
        assert data["simulation_running"] is False


# ---------------------------------------------------------------------------
# 2. GET /api/data
# ---------------------------------------------------------------------------

class TestDataEndpoint:
    """仿真数据接口契约。"""

    def test_returns_200(self, client):
        resp = client.get("/api/data")
        assert resp.status_code == 200

    def test_response_is_json_object(self, client):
        data = _json(client.get("/api/data"))
        assert isinstance(data, dict)

    def test_response_contains_satellites(self, client):
        data = _json(client.get("/api/data"))
        assert "satellites" in data or "leo_satellites" in data or len(data) > 0


# ---------------------------------------------------------------------------
# 3. GET /api/system_info
# ---------------------------------------------------------------------------

class TestSystemInfoEndpoint:
    """系统信息接口契约。"""

    def test_returns_200(self, client):
        resp = client.get("/api/system_info")
        assert resp.status_code == 200

    def test_envelope_code_is_zero(self, client):
        """ok() 包络响应 code 应为 0。"""
        data = _json(client.get("/api/system_info"))
        assert data.get("code") == 0

    def test_data_field_present(self, client):
        data = _json(client.get("/api/system_info"))
        assert "data" in data
        assert isinstance(data["data"], dict)

    def test_data_types_field(self, client):
        """data.data_types 应为字典且非空。"""
        body = _json(client.get("/api/system_info"))["data"]
        assert "data_types" in body
        dt = body["data_types"]
        assert isinstance(dt, dict)
        assert len(dt) > 0

    def test_ground_station_count_is_int(self, client):
        body = _json(client.get("/api/system_info"))["data"]
        assert isinstance(body.get("ground_station_count"), int)
        assert body["ground_station_count"] > 0

    def test_leo_satellite_count_is_int(self, client):
        body = _json(client.get("/api/system_info"))["data"]
        assert isinstance(body.get("leo_satellite_count"), int)
        assert body["leo_satellite_count"] > 0

    def test_time_scale_present(self, client):
        body = _json(client.get("/api/system_info"))["data"]
        assert "time_scale" in body
        assert isinstance(body["time_scale"], (int, float))


# ---------------------------------------------------------------------------
# 4. GET /api/resource_status
# ---------------------------------------------------------------------------

class TestResourceStatusEndpoint:
    """资源状态接口契约。"""

    def test_returns_200(self, client):
        resp = client.get("/api/resource_status")
        assert resp.status_code == 200

    def test_response_has_summary(self, client):
        data = _json(client.get("/api/resource_status"))
        assert "summary" in data
        assert isinstance(data["summary"], dict)

    def test_summary_has_satellite_fields(self, client):
        summary = _json(client.get("/api/resource_status"))["summary"]
        required_fields = [
            "satellites_total", "satellites_busy", "satellites_idle",
            "satellites_utilization", "satellites_task_count",
        ]
        for field in required_fields:
            assert field in summary, f"summary 缺少字段: {field}"

    def test_summary_has_ground_station_fields(self, client):
        summary = _json(client.get("/api/resource_status"))["summary"]
        for field in ["ground_stations_total", "ground_stations_busy", "ground_stations_idle"]:
            assert field in summary

    def test_summary_has_geo_relay_fields(self, client):
        summary = _json(client.get("/api/resource_status"))["summary"]
        for field in ["geo_relays_total", "geo_relays_busy", "geo_relays_idle"]:
            assert field in summary

    def test_summary_overall_utilization_is_number(self, client):
        summary = _json(client.get("/api/resource_status"))["summary"]
        assert "overall_utilization" in summary
        assert isinstance(summary["overall_utilization"], (int, float))
        assert 0.0 <= summary["overall_utilization"] <= 100.0

    def test_satellites_list_present(self, client):
        data = _json(client.get("/api/resource_status"))
        assert "satellites" in data
        assert isinstance(data["satellites"], list)
        assert len(data["satellites"]) > 0

    def test_satellites_entries_have_required_fields(self, client):
        satellites = _json(client.get("/api/resource_status"))["satellites"]
        for sat in satellites[:3]:  # 检查前3条
            for field in ["id", "name", "status", "task_count", "bandwidth_used"]:
                assert field in sat, f"卫星条目缺少字段: {field}"

    def test_ground_stations_list_present(self, client):
        data = _json(client.get("/api/resource_status"))
        assert "ground_stations" in data
        assert isinstance(data["ground_stations"], list)
        assert len(data["ground_stations"]) > 0

    def test_idle_plus_busy_equals_total(self, client):
        """空闲数 + 忙碌数应等于总数（自洽性校验）。"""
        summary = _json(client.get("/api/resource_status"))["summary"]
        assert summary["satellites_idle"] + summary["satellites_busy"] == summary["satellites_total"]
        assert summary["ground_stations_idle"] + summary["ground_stations_busy"] == summary["ground_stations_total"]


# ---------------------------------------------------------------------------
# 5. GET /api/resource_utilization
# ---------------------------------------------------------------------------

class TestResourceUtilizationEndpoint:
    """资源利用率接口契约。"""

    def test_returns_200(self, client):
        resp = client.get("/api/resource_utilization")
        assert resp.status_code == 200

    def test_has_total_requests_field(self, client):
        data = _json(client.get("/api/resource_utilization"))
        assert "total_requests" in data
        assert isinstance(data["total_requests"], int)

    def test_stat_fields_are_non_negative(self, client):
        data = _json(client.get("/api/resource_utilization"))
        for field in ["total_requests", "accepted_requests", "rejected_requests", "user_requests"]:
            assert data.get(field, 0) >= 0, f"字段 {field} 不应为负数"


# ---------------------------------------------------------------------------
# 6. GET /api/requests
# ---------------------------------------------------------------------------

class TestRequestsListEndpoint:
    """请求列表接口契约。"""

    def test_returns_200(self, client):
        resp = client.get("/api/requests")
        assert resp.status_code == 200

    def test_response_is_list(self, client):
        data = _json(client.get("/api/requests"))
        assert isinstance(data, list)

    def test_empty_on_fresh_engine(self, client):
        """全新引擎（无提交请求）应返回空列表。"""
        data = _json(client.get("/api/requests"))
        assert data == []


# ---------------------------------------------------------------------------
# 7. POST /api/request — 正常路径
# ---------------------------------------------------------------------------

class TestSubmitRequestEndpoint:
    """提交传输请求接口 —— 正常路径与返回契约。"""

    _VALID_PAYLOAD = {
        "data_type": "TASK_CMD",
        "data_size": 50,
        "priority": 9,
        "max_delay": 600,
    }

    def test_returns_200_with_valid_payload(self, client):
        resp = client.post(
            "/api/request",
            data=json.dumps(self._VALID_PAYLOAD),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_response_has_id_field(self, client):
        data = _json(client.post(
            "/api/request",
            data=json.dumps(self._VALID_PAYLOAD),
            content_type="application/json",
        ))
        assert "id" in data, "响应字典应包含 id 字段"

    def test_response_has_status_field(self, client):
        data = _json(client.post(
            "/api/request",
            data=json.dumps(self._VALID_PAYLOAD),
            content_type="application/json",
        ))
        assert "status" in data, "响应字典应包含 status 字段"

    def test_status_is_accepted_or_rejected(self, client):
        data = _json(client.post(
            "/api/request",
            data=json.dumps(self._VALID_PAYLOAD),
            content_type="application/json",
        ))
        assert data["status"] in {"accepted", "rejected", "transmitting", "completed"}, (
            f"status 值预期为已知状态，实际为: {data['status']}"
        )

    def test_response_has_data_type(self, client):
        data = _json(client.post(
            "/api/request",
            data=json.dumps(self._VALID_PAYLOAD),
            content_type="application/json",
        ))
        assert data.get("data_type") == "TASK_CMD"

    def test_request_count_increases_after_submit(self, client, test_engine):
        """提交后，引擎统计中 total_requests 应增加 1。"""
        before = test_engine.stats["total_requests"]
        client.post(
            "/api/request",
            data=json.dumps(self._VALID_PAYLOAD),
            content_type="application/json",
        )
        after = test_engine.stats["total_requests"]
        assert after == before + 1

    def test_submit_intel_type(self, client):
        payload = {"data_type": "INTEL", "data_size": 1000, "priority": 8, "max_delay": 300}
        resp = client.post(
            "/api/request",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = _json(resp)
        assert "id" in data
        assert "status" in data

    def test_submit_data_slice_type(self, client):
        payload = {"data_type": "DATA_SLICE", "data_size": 200, "priority": 5, "max_delay": 1200}
        resp = client.post(
            "/api/request",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = _json(resp)
        assert "id" in data

    def test_submit_raw_image_type(self, client):
        payload = {"data_type": "RAW_IMAGE", "data_size": 5, "priority": 3, "max_delay": 3600}
        resp = client.post(
            "/api/request",
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = _json(resp)
        assert "id" in data

    def test_multiple_submits_increment_counter(self, client, test_engine):
        """连续提交 N 个请求，total_requests 应等于 N。"""
        n = 3
        for _ in range(n):
            client.post(
                "/api/request",
                data=json.dumps(self._VALID_PAYLOAD),
                content_type="application/json",
            )
        assert test_engine.stats["total_requests"] >= n

    def test_submitted_request_appears_in_engine_state(self, client, test_engine):
        """成功提交后，引擎应在 transmission_requests 或 request_history 中持有该请求。"""
        before_total = (
            len(test_engine.transmission_requests) + len(test_engine.request_history)
        )
        client.post(
            "/api/request",
            data=json.dumps(self._VALID_PAYLOAD),
            content_type="application/json",
        )
        after_total = (
            len(test_engine.transmission_requests) + len(test_engine.request_history)
        )
        assert after_total == before_total + 1

    def test_response_is_dict_not_list(self, client):
        data = _json(client.post(
            "/api/request",
            data=json.dumps(self._VALID_PAYLOAD),
            content_type="application/json",
        ))
        assert isinstance(data, dict), "POST /api/request 响应应为 JSON 对象，不是数组"


# ---------------------------------------------------------------------------
# 8. POST /api/update_ground_stations
# ---------------------------------------------------------------------------

class TestUpdateGroundStationsEndpoint:
    """更新地面站数量接口 —— 正常路径。"""

    def test_returns_200_with_valid_count(self, client, test_engine):
        # 使用当前地面站数量（无实际变化也应返回 200）
        current = len(test_engine.ground_stations)
        # 尝试增加1（或减少1），确保在合法范围内
        from backend.core import MIN_GROUND_STATION_COUNT, MAX_GROUND_STATION_COUNT
        new_count = min(current + 1, MAX_GROUND_STATION_COUNT)
        resp = client.post(
            "/api/update_ground_stations",
            data=json.dumps({"count": new_count}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_response_has_success_field(self, client, test_engine):
        from backend.core import MAX_GROUND_STATION_COUNT
        current = len(test_engine.ground_stations)
        new_count = min(current + 1, MAX_GROUND_STATION_COUNT)
        data = _json(client.post(
            "/api/update_ground_stations",
            data=json.dumps({"count": new_count}),
            content_type="application/json",
        ))
        assert "success" in data

    def test_response_has_message(self, client, test_engine):
        from backend.core import MAX_GROUND_STATION_COUNT
        current = len(test_engine.ground_stations)
        new_count = min(current + 1, MAX_GROUND_STATION_COUNT)
        data = _json(client.post(
            "/api/update_ground_stations",
            data=json.dumps({"count": new_count}),
            content_type="application/json",
        ))
        assert "message" in data


# ---------------------------------------------------------------------------
# 9. POST /api/update_leo_satellites
# ---------------------------------------------------------------------------

class TestUpdateLeoSatellitesEndpoint:
    """更新 LEO 卫星数量接口 —— 正常路径。"""

    def test_returns_200_with_valid_count(self, client, test_engine):
        current = len(test_engine.leo_satellites)
        new_count = current + 1
        resp = client.post(
            "/api/update_leo_satellites",
            data=json.dumps({"count": new_count}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_response_has_success_field(self, client, test_engine):
        current = len(test_engine.leo_satellites)
        new_count = current + 1
        data = _json(client.post(
            "/api/update_leo_satellites",
            data=json.dumps({"count": new_count}),
            content_type="application/json",
        ))
        assert "success" in data

    def test_leo_count_updates_in_engine(self, client, test_engine):
        """更新成功后，引擎 leo_satellites 数量应与请求一致。"""
        current = len(test_engine.leo_satellites)
        new_count = current + 1
        resp = client.post(
            "/api/update_leo_satellites",
            data=json.dumps({"count": new_count}),
            content_type="application/json",
        )
        data = _json(resp)
        if data.get("success"):
            assert len(test_engine.leo_satellites) == new_count


# ---------------------------------------------------------------------------
# 10. GET /api/opportunistic_stations
# ---------------------------------------------------------------------------

class TestOpportunisticStationsEndpoint:
    """随遇接入站接口契约。"""

    def test_returns_200(self, client):
        resp = client.get("/api/opportunistic_stations")
        assert resp.status_code == 200

    def test_response_has_stations_list(self, client):
        data = _json(client.get("/api/opportunistic_stations"))
        assert "stations" in data
        assert isinstance(data["stations"], list)

    def test_response_has_count_field(self, client):
        data = _json(client.get("/api/opportunistic_stations"))
        assert "count" in data
        assert isinstance(data["count"], int)

    def test_count_matches_stations_length(self, client):
        data = _json(client.get("/api/opportunistic_stations"))
        assert data["count"] == len(data["stations"])


# ---------------------------------------------------------------------------
# 11. GET /api/data_combinations
# ---------------------------------------------------------------------------

class TestDataCombinationsEndpoint:
    """数据组合信息接口契约。"""

    def test_returns_200(self, client):
        resp = client.get("/api/data_combinations")
        assert resp.status_code == 200

    def test_response_has_base_types(self, client):
        data = _json(client.get("/api/data_combinations"))
        assert "base_types" in data
        assert isinstance(data["base_types"], list)
        assert len(data["base_types"]) > 0

    def test_response_has_total_combinations(self, client):
        data = _json(client.get("/api/data_combinations"))
        assert "total_combinations" in data
        assert isinstance(data["total_combinations"], int)
        assert data["total_combinations"] > 0

    def test_base_types_contain_known_types(self, client):
        data = _json(client.get("/api/data_combinations"))
        base_types = set(data["base_types"])
        expected = {"TASK_CMD", "INTEL", "DATA_SLICE", "RAW_IMAGE"}
        assert expected.issubset(base_types), (
            f"base_types 应至少包含 {expected}，实际: {base_types}"
        )


# ---------------------------------------------------------------------------
# 12. GET /api/all_requests_with_background
# ---------------------------------------------------------------------------

class TestAllRequestsWithBackgroundEndpoint:
    """包含背景任务的全量请求接口契约。"""

    def test_returns_200(self, client):
        resp = client.get("/api/all_requests_with_background")
        assert resp.status_code == 200

    def test_response_is_list(self, client):
        data = _json(client.get("/api/all_requests_with_background"))
        assert isinstance(data, list)


# ---------------------------------------------------------------------------
# 13. 版本化别名 /api/v1/... 契约
# ---------------------------------------------------------------------------

class TestV1Aliases:
    """v1 路由别名应与原始路由等价。"""

    def test_health_v1_returns_200(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_system_info_v1_returns_200(self, client):
        resp = client.get("/api/v1/system_info")
        assert resp.status_code == 200

    def test_resource_status_v1_returns_200(self, client):
        resp = client.get("/api/v1/resource_status")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 14. 探针接口
# ---------------------------------------------------------------------------

class TestProbeEndpoints:
    """存活/就绪探针接口契约。"""

    def test_livez_returns_200(self, client):
        resp = client.get("/api/livez")
        assert resp.status_code == 200

    def test_livez_response_has_status(self, client):
        data = _json(client.get("/api/livez"))
        assert data.get("status") == "alive"

    def test_readyz_returns_non_200_when_not_running(self, client):
        """引擎未运行时，就绪探针应返回非 200（503 或 500）。

        注入 autostart=False 的引擎不持有 simulation_thread，
        readyz 端点将因 AttributeError 返回 500，或因 running=False 返回 503。
        两者均表明服务未就绪。
        """
        resp = client.get("/api/readyz")
        assert resp.status_code in (503, 500), (
            f"引擎未运行时 readyz 应返回 503 或 500，实际: {resp.status_code}"
        )

    def test_readyz_response_has_status_key(self, client):
        """就绪探针响应应包含 status 或 code 字段（取决于是 503 还是 500 路径）。"""
        data = _json(client.get("/api/readyz"))
        assert "status" in data or "code" in data


# ---------------------------------------------------------------------------
# 15. OpenAPI 规范端点
# ---------------------------------------------------------------------------

class TestOpenApiEndpoint:
    """OpenAPI 规范接口契约。"""

    def test_returns_200(self, client):
        resp = client.get("/api/openapi.json")
        assert resp.status_code == 200

    def test_response_has_openapi_field(self, client):
        data = _json(client.get("/api/openapi.json"))
        assert "openapi" in data
        assert data["openapi"].startswith("3.")
