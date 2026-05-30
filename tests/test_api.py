# -*- coding: utf-8 -*-
"""首批 API 回归测试 —— 覆盖核心端点的正常路径与基本契约。

使用 Flask test_client 对以下接口进行集成测试：
  - GET  /api/health         : 健康检查
  - GET  /api/data           : 仿真数据
  - GET  /api/system_info    : 系统配置信息
  - GET  /api/requests       : 传输请求列表
  - GET  /api/resource_utilization : 资源利用率
  - GET  /api/livez          : 存活探针
  - POST /api/request        : 提交传输请求（合法载荷 / 缺字段校验 / 无效卫星拒绝）
  - POST /api/update_ground_stations : 地面站数量更新边界校验
  - POST /api/update_leo_satellites  : LEO 卫星数量更新边界校验

测试策略：
  - 注入 create_engine(seed=0, autostart=False) 的干净引擎，不依赖真实后台线程
  - 不设置 SMARTNODE_API_KEY，走「开放」模式（g.identity.role = admin）
  - 仅断言 HTTP 状态码、关键 JSON 字段与类型，避免对可变仿真数值做硬编码断言
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from backend.core import create_engine


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def _engine():
    """函数作用域内的隔离引擎（固定种子、不启动线程）。"""
    eng = create_engine(seed=0, autostart=False)
    yield eng
    eng.running = False


@pytest.fixture
def client(_engine):
    """将干净引擎注入 api.app，返回 Flask test_client。

    测试结束后恢复原始引擎，避免全局状态污染。
    """
    import backend.api as api_module

    original = api_module.simulation_engine
    api_module.simulation_engine = _engine
    api_module.app.config["TESTING"] = True
    try:
        with api_module.app.test_client() as c:
            yield c
    finally:
        api_module.simulation_engine = original


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _json(resp) -> dict:
    """从 Response 中解析 JSON 字典。"""
    return json.loads(resp.data.decode("utf-8"))


def _post_json(client, url: str, payload: dict):
    return client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
    )


# ---------------------------------------------------------------------------
# 1. GET /api/health
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """健康检查接口基本契约。"""

    def test_status_200(self, client):
        assert client.get("/api/health").status_code == 200

    def test_success_true(self, client):
        assert _json(client.get("/api/health"))["success"] is True

    def test_service_field_is_string(self, client):
        data = _json(client.get("/api/health"))
        assert "service" in data
        assert isinstance(data["service"], str)

    def test_simulation_running_is_bool(self, client):
        data = _json(client.get("/api/health"))
        assert isinstance(data.get("simulation_running"), bool)

    def test_simulation_not_running_with_test_engine(self, client):
        """注入 autostart=False 引擎时 simulation_running 应为 False。"""
        assert _json(client.get("/api/health"))["simulation_running"] is False


# ---------------------------------------------------------------------------
# 2. GET /api/data
# ---------------------------------------------------------------------------


class TestDataEndpoint:
    """仿真数据接口基本契约。"""

    def test_status_200(self, client):
        assert client.get("/api/data").status_code == 200

    def test_response_is_dict(self, client):
        assert isinstance(_json(client.get("/api/data")), dict)

    def test_response_is_nonempty(self, client):
        assert len(_json(client.get("/api/data"))) > 0


# ---------------------------------------------------------------------------
# 3. GET /api/system_info
# ---------------------------------------------------------------------------


class TestSystemInfoEndpoint:
    """系统信息接口契约。"""

    def test_status_200(self, client):
        assert client.get("/api/system_info").status_code == 200

    def test_envelope_code_zero(self, client):
        """ok() 包络响应 code 应为 0。"""
        assert _json(client.get("/api/system_info")).get("code") == 0

    def test_data_field_is_dict(self, client):
        body = _json(client.get("/api/system_info"))
        assert "data" in body
        assert isinstance(body["data"], dict)

    def test_ground_station_count_positive_int(self, client):
        body = _json(client.get("/api/system_info"))["data"]
        count = body.get("ground_station_count")
        assert isinstance(count, int) and count > 0

    def test_leo_satellite_count_positive_int(self, client):
        body = _json(client.get("/api/system_info"))["data"]
        count = body.get("leo_satellite_count")
        assert isinstance(count, int) and count > 0

    def test_data_types_nonempty_dict(self, client):
        body = _json(client.get("/api/system_info"))["data"]
        dt = body.get("data_types")
        assert isinstance(dt, dict) and len(dt) > 0

    def test_time_scale_is_number(self, client):
        body = _json(client.get("/api/system_info"))["data"]
        assert isinstance(body.get("time_scale"), (int, float))


# ---------------------------------------------------------------------------
# 4. GET /api/requests
# ---------------------------------------------------------------------------


class TestRequestsListEndpoint:
    """传输请求列表接口。"""

    def test_status_200(self, client):
        assert client.get("/api/requests").status_code == 200

    def test_response_is_list(self, client):
        assert isinstance(_json(client.get("/api/requests")), list)


# ---------------------------------------------------------------------------
# 5. GET /api/resource_utilization
# ---------------------------------------------------------------------------


class TestResourceUtilizationEndpoint:
    """资源利用率接口基本字段检验。"""

    def test_status_200(self, client):
        assert client.get("/api/resource_utilization").status_code == 200

    def test_total_requests_is_int(self, client):
        data = _json(client.get("/api/resource_utilization"))
        assert isinstance(data.get("total_requests"), int)

    def test_accepted_and_rejected_fields_present(self, client):
        data = _json(client.get("/api/resource_utilization"))
        assert "accepted_requests" in data
        assert "rejected_requests" in data


# ---------------------------------------------------------------------------
# 6. GET /api/livez
# ---------------------------------------------------------------------------


class TestLivenessProbe:
    """存活探针契约。"""

    def test_status_200(self, client):
        assert client.get("/api/livez").status_code == 200

    def test_status_field_is_alive(self, client):
        assert _json(client.get("/api/livez")).get("status") == "alive"


# ---------------------------------------------------------------------------
# 7. POST /api/request  —— 提交传输请求
# ---------------------------------------------------------------------------


_VALID_PAYLOAD = {
    "data_type": "TASK_CMD",
    "data_size": 512,
    "priority": 5,
    "max_delay": 600,
}


class TestSubmitRequestEndpoint:
    """提交请求端点的正常路径与校验分支。"""

    def test_valid_payload_returns_200_or_accepted(self, client):
        resp = _post_json(client, "/api/request", _VALID_PAYLOAD)
        # 开放模式下应为 200（接受）或 400（资源不足时引擎拒绝）
        assert resp.status_code in (200, 400)

    def test_valid_payload_returns_dict(self, client):
        resp = _post_json(client, "/api/request", _VALID_PAYLOAD)
        assert isinstance(_json(resp), dict)

    def test_missing_data_type_returns_400_or_422(self, client):
        """缺少必填字段应被校验层拦截并返回 4xx。"""
        bad = {k: v for k, v in _VALID_PAYLOAD.items() if k != "data_type"}
        resp = _post_json(client, "/api/request", bad)
        assert resp.status_code in (400, 422)

    def test_invalid_priority_out_of_range_returns_4xx(self, client):
        """priority 超出 0-10 范围应被校验层拦截并返回 4xx。"""
        bad = {**_VALID_PAYLOAD, "priority": 999}
        resp = _post_json(client, "/api/request", bad)
        assert resp.status_code in (400, 422)

    def test_invalid_satellite_id_returns_400(self, client):
        """指定不存在的卫星 ID 时，引擎应返回 error 并由路由映射到 400。"""
        payload = {**_VALID_PAYLOAD, "satellite_id": "INVALID_SAT_XYZ"}
        resp = _post_json(client, "/api/request", payload)
        assert resp.status_code == 400

    def test_invalid_satellite_id_response_has_error(self, client):
        payload = {**_VALID_PAYLOAD, "satellite_id": "INVALID_SAT_XYZ"}
        data = _json(_post_json(client, "/api/request", payload))
        # 拒绝响应应包含 status=error 或错误说明字段
        assert data.get("status") == "error" or "error" in data or "reject_reason" in data

    def test_non_json_body_returns_4xx(self, client):
        """非 JSON body 应返回 4xx 而非 5xx。"""
        resp = client.post("/api/request", data="not-json", content_type="text/plain")
        assert resp.status_code in (400, 415, 422)


# ---------------------------------------------------------------------------
# 8. POST /api/update_ground_stations  —— 边界校验
# ---------------------------------------------------------------------------


class TestUpdateGroundStationsEndpoint:
    """地面站数量更新接口的边界与校验。"""

    def test_valid_count_returns_200(self, client):
        resp = _post_json(client, "/api/update_ground_stations", {"count": 10})
        assert resp.status_code == 200

    def test_valid_count_response_has_success(self, client):
        data = _json(_post_json(client, "/api/update_ground_stations", {"count": 10}))
        assert "success" in data

    def test_count_below_min_returns_4xx(self, client):
        """count=0 低于最小值（5），应被校验层拦截。"""
        resp = _post_json(client, "/api/update_ground_stations", {"count": 0})
        assert resp.status_code in (400, 422)

    def test_missing_count_field_returns_4xx(self, client):
        resp = _post_json(client, "/api/update_ground_stations", {"wrong_field": 10})
        assert resp.status_code in (400, 422)

    def test_non_json_returns_4xx(self, client):
        resp = client.post(
            "/api/update_ground_stations",
            data="count=10",
            content_type="application/x-www-form-urlencoded",
        )
        assert resp.status_code in (400, 415)


# ---------------------------------------------------------------------------
# 9. POST /api/update_leo_satellites  —— 边界校验
# ---------------------------------------------------------------------------


class TestUpdateLeoSatellitesEndpoint:
    """LEO 卫星数量更新接口的边界与校验。"""

    def test_valid_count_returns_200(self, client):
        resp = _post_json(client, "/api/update_leo_satellites", {"count": 6})
        assert resp.status_code == 200

    def test_valid_count_response_has_success(self, client):
        data = _json(_post_json(client, "/api/update_leo_satellites", {"count": 6}))
        assert "success" in data

    def test_count_zero_returns_4xx(self, client):
        """count=0 低于最小值（1），应被校验层拦截。"""
        resp = _post_json(client, "/api/update_leo_satellites", {"count": 0})
        assert resp.status_code in (400, 422)

    def test_missing_count_field_returns_4xx(self, client):
        resp = _post_json(client, "/api/update_leo_satellites", {})
        assert resp.status_code in (400, 422)

    def test_non_json_returns_4xx(self, client):
        resp = client.post(
            "/api/update_leo_satellites",
            data="count=6",
            content_type="application/x-www-form-urlencoded",
        )
        assert resp.status_code in (400, 415)
