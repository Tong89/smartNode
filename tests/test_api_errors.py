# -*- coding: utf-8 -*-
"""接口错误路径集成测试。

针对 POST /api/update_ground_stations、POST /api/update_leo_satellites 以及
POST /api/request 接口的非法/缺失参数、越界、坏 JSON 等错误路径做覆盖：

  - count 缺失                → 400 VALIDATION_ERROR
  - count 为非整数（浮点/字符串）→ 400 VALIDATION_ERROR
  - count 越下界              → 400 VALIDATION_ERROR
  - count 越上界（仅 GS）     → 400 VALIDATION_ERROR
  - 请求体不是 JSON           → 400/415
  - /api/request 坏 JSON      → 400/415
  - /api/request 缺必填字段   → 400 VALIDATION_ERROR
  - /api/request 指定不存在卫星 → 400，status="error"
  - /api/request 数据类型非法  → 400 VALIDATION_ERROR

测试仅使用 flask_client_engine fixture（来自 conftest.py）。
"""

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from backend.core import (
    MAX_GROUND_STATION_COUNT,
    MIN_GROUND_STATION_COUNT,
    MIN_LEO_SATELLITE_COUNT,
)


# ---------------------------------------------------------------------------
# Auto-reset rate-limiter state so tests never trip over accumulated hits.
# The limiter is a module-level singleton in backend.ratelimit; we clear its
# internal hit-window dict before each test function.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Clear the global sliding-window rate limiter before every test."""
    from backend.ratelimit import _limiter
    with _limiter._lock:
        _limiter._hits.clear()
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json(resp):
    return json.loads(resp.data.decode("utf-8"))


def _post_gs(client, payload, content_type="application/json"):
    return client.post(
        "/api/update_ground_stations",
        data=json.dumps(payload) if isinstance(payload, dict) else payload,
        content_type=content_type,
    )


def _post_leo(client, payload, content_type="application/json"):
    return client.post(
        "/api/update_leo_satellites",
        data=json.dumps(payload) if isinstance(payload, dict) else payload,
        content_type=content_type,
    )


def _post_req(client, payload, content_type="application/json"):
    return client.post(
        "/api/request",
        data=json.dumps(payload) if isinstance(payload, dict) else payload,
        content_type=content_type,
    )


# ---------------------------------------------------------------------------
# POST /api/update_ground_stations — 错误路径
# ---------------------------------------------------------------------------

class TestUpdateGroundStationsErrors:
    """update_ground_stations 接口的错误路径覆盖。"""

    def test_missing_count_returns_400(self, flask_client):
        resp = _post_gs(flask_client, {})
        assert resp.status_code == 400

    def test_missing_count_has_error_code(self, flask_client):
        data = _json(_post_gs(flask_client, {}))
        assert data.get("code") == "VALIDATION_ERROR"

    def test_missing_count_has_error_details(self, flask_client):
        data = _json(_post_gs(flask_client, {}))
        assert "details" in data

    def test_float_count_returns_400(self, flask_client):
        resp = _post_gs(flask_client, {"count": 7.5})
        assert resp.status_code == 400

    def test_string_count_returns_400(self, flask_client):
        resp = _post_gs(flask_client, {"count": "10"})
        assert resp.status_code == 400

    def test_bool_count_returns_400(self, flask_client):
        """bool 是 int 的子类，但业务上应被拒绝。"""
        resp = _post_gs(flask_client, {"count": True})
        assert resp.status_code == 400

    def test_null_count_returns_400(self, flask_client):
        resp = _post_gs(flask_client, {"count": None})
        assert resp.status_code == 400

    def test_below_min_count_returns_400(self, flask_client):
        resp = _post_gs(flask_client, {"count": MIN_GROUND_STATION_COUNT - 1})
        assert resp.status_code == 400

    def test_above_max_count_returns_400(self, flask_client):
        resp = _post_gs(flask_client, {"count": MAX_GROUND_STATION_COUNT + 1})
        assert resp.status_code == 400

    def test_above_max_has_validation_error_code(self, flask_client):
        data = _json(_post_gs(flask_client, {"count": MAX_GROUND_STATION_COUNT + 1}))
        assert data.get("code") == "VALIDATION_ERROR"

    def test_non_json_body_returns_4xx(self, flask_client):
        resp = _post_gs(flask_client, "not-json", content_type="text/plain")
        assert resp.status_code in (400, 415)

    def test_empty_body_returns_4xx(self, flask_client):
        resp = flask_client.post(
            "/api/update_ground_stations",
            data=b"",
            content_type="application/json",
        )
        assert resp.status_code in (400, 415)

    def test_unknown_field_returns_400(self, flask_client):
        resp = _post_gs(flask_client, {"count": MIN_GROUND_STATION_COUNT, "extra": "bad"})
        assert resp.status_code == 400

    def test_error_response_has_status_error(self, flask_client):
        data = _json(_post_gs(flask_client, {"count": "bad"}))
        assert data.get("status") == "error"

    def test_error_response_has_message(self, flask_client):
        data = _json(_post_gs(flask_client, {}))
        assert "message" in data

    def test_error_response_has_request_id(self, flask_client):
        data = _json(_post_gs(flask_client, {}))
        assert "request_id" in data


# ---------------------------------------------------------------------------
# POST /api/update_leo_satellites — 错误路径
# ---------------------------------------------------------------------------

class TestUpdateLeoSatellitesErrors:
    """update_leo_satellites 接口的错误路径覆盖。"""

    def test_missing_count_returns_400(self, flask_client):
        resp = _post_leo(flask_client, {})
        assert resp.status_code == 400

    def test_missing_count_has_error_code(self, flask_client):
        data = _json(_post_leo(flask_client, {}))
        assert data.get("code") == "VALIDATION_ERROR"

    def test_float_count_returns_400(self, flask_client):
        resp = _post_leo(flask_client, {"count": 3.5})
        assert resp.status_code == 400

    def test_string_count_returns_400(self, flask_client):
        resp = _post_leo(flask_client, {"count": "five"})
        assert resp.status_code == 400

    def test_bool_count_returns_400(self, flask_client):
        resp = _post_leo(flask_client, {"count": False})
        assert resp.status_code == 400

    def test_below_min_count_returns_400(self, flask_client):
        resp = _post_leo(flask_client, {"count": MIN_LEO_SATELLITE_COUNT - 1})
        assert resp.status_code == 400

    def test_zero_count_returns_400(self, flask_client):
        """0 卫星低于最小值 1。"""
        resp = _post_leo(flask_client, {"count": 0})
        assert resp.status_code == 400

    def test_negative_count_returns_400(self, flask_client):
        resp = _post_leo(flask_client, {"count": -5})
        assert resp.status_code == 400

    def test_non_json_body_returns_4xx(self, flask_client):
        resp = _post_leo(flask_client, "garbage", content_type="text/plain")
        assert resp.status_code in (400, 415)

    def test_empty_body_returns_4xx(self, flask_client):
        resp = flask_client.post(
            "/api/update_leo_satellites",
            data=b"",
            content_type="application/json",
        )
        assert resp.status_code in (400, 415)

    def test_unknown_field_returns_400(self, flask_client):
        resp = _post_leo(flask_client, {"count": MIN_LEO_SATELLITE_COUNT, "hack": True})
        assert resp.status_code == 400

    def test_error_response_has_status_error(self, flask_client):
        data = _json(_post_leo(flask_client, {"count": 0}))
        assert data.get("status") == "error"

    def test_error_response_has_request_id(self, flask_client):
        data = _json(_post_leo(flask_client, {}))
        assert "request_id" in data

    def test_details_field_present_on_validation_failure(self, flask_client):
        data = _json(_post_leo(flask_client, {"count": "not_a_number"}))
        assert "details" in data


# ---------------------------------------------------------------------------
# POST /api/request — 错误路径
# ---------------------------------------------------------------------------

class TestSubmitRequestErrors:
    """submit_transmission_request 接口的错误路径覆盖。"""

    _BASE_VALID = {
        "data_type": "TASK_CMD",
        "data_size": 50,
        "priority": 7,
        "max_delay": 300,
    }

    def test_missing_data_type_returns_400(self, flask_client):
        payload = {"data_size": 50, "priority": 5}
        resp = _post_req(flask_client, payload)
        assert resp.status_code == 400

    def test_missing_data_type_has_validation_error(self, flask_client):
        data = _json(_post_req(flask_client, {"data_size": 50}))
        assert data.get("code") == "VALIDATION_ERROR"

    def test_missing_data_size_returns_400(self, flask_client):
        payload = {"data_type": "TASK_CMD", "priority": 5}
        resp = _post_req(flask_client, payload)
        assert resp.status_code == 400

    def test_invalid_data_type_returns_400(self, flask_client):
        payload = dict(self._BASE_VALID)
        payload["data_type"] = "UNKNOWN_TYPE_XYZ"
        resp = _post_req(flask_client, payload)
        assert resp.status_code == 400

    def test_invalid_data_type_has_validation_error_code(self, flask_client):
        payload = dict(self._BASE_VALID)
        payload["data_type"] = "NOT_A_TYPE"
        data = _json(_post_req(flask_client, payload))
        assert data.get("code") == "VALIDATION_ERROR"

    def test_empty_data_type_returns_400(self, flask_client):
        payload = dict(self._BASE_VALID)
        payload["data_type"] = ""
        resp = _post_req(flask_client, payload)
        assert resp.status_code == 400

    def test_zero_data_size_returns_400(self, flask_client):
        payload = dict(self._BASE_VALID)
        payload["data_size"] = 0
        resp = _post_req(flask_client, payload)
        assert resp.status_code == 400

    def test_negative_data_size_returns_400(self, flask_client):
        payload = dict(self._BASE_VALID)
        payload["data_size"] = -10
        resp = _post_req(flask_client, payload)
        assert resp.status_code == 400

    def test_non_numeric_data_size_returns_400(self, flask_client):
        payload = dict(self._BASE_VALID)
        payload["data_size"] = "big"
        resp = _post_req(flask_client, payload)
        assert resp.status_code == 400

    def test_out_of_range_priority_returns_400(self, flask_client):
        payload = dict(self._BASE_VALID)
        payload["priority"] = 99
        resp = _post_req(flask_client, payload)
        assert resp.status_code == 400

    def test_negative_priority_returns_400(self, flask_client):
        payload = dict(self._BASE_VALID)
        payload["priority"] = -1
        resp = _post_req(flask_client, payload)
        assert resp.status_code == 400

    def test_string_priority_returns_400(self, flask_client):
        payload = dict(self._BASE_VALID)
        payload["priority"] = "high"
        resp = _post_req(flask_client, payload)
        assert resp.status_code == 400

    def test_negative_max_delay_returns_400(self, flask_client):
        payload = dict(self._BASE_VALID)
        payload["max_delay"] = -5
        resp = _post_req(flask_client, payload)
        assert resp.status_code == 400

    def test_non_json_body_returns_4xx(self, flask_client):
        resp = _post_req(flask_client, "not-json", content_type="text/plain")
        assert resp.status_code in (400, 415)

    def test_empty_body_returns_4xx(self, flask_client):
        resp = flask_client.post(
            "/api/request",
            data=b"",
            content_type="application/json",
        )
        assert resp.status_code in (400, 415)

    def test_unknown_field_rejected(self, flask_client):
        payload = dict(self._BASE_VALID)
        payload["injected_field"] = "evil"
        resp = _post_req(flask_client, payload)
        assert resp.status_code == 400

    def test_nonexistent_satellite_returns_400(self, flask_client):
        """指定不存在的卫星 ID，API 层应返回 400，status='error'。"""
        payload = dict(self._BASE_VALID)
        payload["satellite_id"] = "DEFINITELY_NOT_A_REAL_SAT_ID_99999"
        resp = _post_req(flask_client, payload)
        assert resp.status_code == 400

    def test_nonexistent_satellite_has_error_status(self, flask_client):
        payload = dict(self._BASE_VALID)
        payload["satellite_id"] = "BOGUS_SAT_XXXX"
        data = _json(_post_req(flask_client, payload))
        assert data.get("status") == "error"

    def test_nonexistent_satellite_response_is_dict(self, flask_client):
        payload = dict(self._BASE_VALID)
        payload["satellite_id"] = "NO_SUCH_SAT"
        data = _json(_post_req(flask_client, payload))
        assert isinstance(data, dict)

    def test_nonexistent_satellite_available_satellites_listed(self, flask_client):
        """错误响应应包含可用卫星列表，帮助客户端自我修正。"""
        payload = dict(self._BASE_VALID)
        payload["satellite_id"] = "MISSING_SAT_00"
        data = _json(_post_req(flask_client, payload))
        assert "available_satellites" in data

    def test_error_details_contains_field_info(self, flask_client):
        """VALIDATION_ERROR 响应应包含 details 字段列表。"""
        data = _json(_post_req(flask_client, {"data_size": 50}))
        assert isinstance(data.get("details"), list)

    def test_validation_error_details_reference_field(self, flask_client):
        data = _json(_post_req(flask_client, {"data_size": 50}))
        fields = [d.get("field") for d in data.get("details", [])]
        assert "data_type" in fields
