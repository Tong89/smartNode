# -*- coding: utf-8 -*-
"""tests/test_store.py — 多场景库 ScenarioStore 单元测试。"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from backend.core import create_engine
from backend.store import ScenarioStore


@pytest.fixture
def engine():
    eng = create_engine(seed=0, autostart=False)
    yield eng
    eng.running = False


@pytest.fixture
def store():
    """每次测试使用独立的内存 SQLite 场景库。"""
    s = ScenarioStore(":memory:")
    yield s
    s.close()


def _mock_stats():
    return {
        "total_requests": 20,
        "accepted_requests": 16,
        "rejected_requests": 4,
        "completed_requests": 14,
        "decision_metrics": {
            "acceptance_rate": 0.8,
            "completion_rate": 0.875,
            "avg_scheduling_time": 5.2,
            "avg_transmission_time": 120.0,
            "throughput_mbps": 150.0,
        },
        "rejection_distribution": {"NO_VISIBLE_GS": 2, "RESOURCE_BUSY": 2},
    }


class TestScenarioStoreBasic:
    def test_list_empty(self, store):
        assert store.list_scenarios() == []

    def test_save_and_list(self, engine, store):
        store.save_scenario("基准", engine, _mock_stats())
        items = store.list_scenarios()
        assert len(items) == 1
        assert items[0]["name"] == "基准"
        assert items[0]["is_baseline"] is False

    def test_save_upserts(self, engine, store):
        store.save_scenario("基准", engine, _mock_stats())
        store.save_scenario("基准", engine, _mock_stats())
        assert len(store.list_scenarios()) == 1

    def test_save_multiple(self, engine, store):
        store.save_scenario("场景A", engine, _mock_stats())
        store.save_scenario("场景B", engine, _mock_stats())
        items = store.list_scenarios()
        names = {i["name"] for i in items}
        assert {"场景A", "场景B"} == names

    def test_load_scenario(self, engine, store):
        store.save_scenario("基准", engine, _mock_stats())
        rec = store.load_scenario("基准")
        assert rec is not None
        assert rec["name"] == "基准"
        assert "run_stats" in rec
        assert rec["run_stats"]["decision_metrics"]["acceptance_rate"] == pytest.approx(0.8)

    def test_load_missing(self, store):
        assert store.load_scenario("不存在") is None

    def test_delete_scenario(self, engine, store):
        store.save_scenario("临时", engine)
        assert store.delete_scenario("临时") is True
        assert store.load_scenario("临时") is None

    def test_delete_missing(self, store):
        assert store.delete_scenario("不存在") is False


class TestScenarioStoreBaseline:
    def test_set_baseline(self, engine, store):
        store.save_scenario("基准", engine)
        store.save_scenario("扩容", engine)
        assert store.set_baseline("基准") is True
        baseline = store.get_baseline()
        assert baseline is not None
        assert baseline["name"] == "基准"
        assert baseline["is_baseline"] is True

    def test_set_baseline_switches(self, engine, store):
        store.save_scenario("基准", engine)
        store.save_scenario("扩容", engine)
        store.set_baseline("基准")
        store.set_baseline("扩容")
        baseline = store.get_baseline()
        assert baseline["name"] == "扩容"
        # 旧基线应被清除
        old = store.load_scenario("基准")
        assert old["is_baseline"] is False

    def test_set_baseline_missing(self, store):
        assert store.set_baseline("不存在") is False

    def test_get_baseline_none(self, store):
        assert store.get_baseline() is None


class TestScenarioStoreCompare:
    def test_compare_basic(self, engine, store):
        stats_a = _mock_stats()
        stats_b = {**_mock_stats(), "decision_metrics": {
            "acceptance_rate": 0.9,
            "completion_rate": 0.95,
            "avg_scheduling_time": 4.0,
            "avg_transmission_time": 100.0,
            "throughput_mbps": 200.0,
        }}
        store.save_scenario("基准", engine, stats_a)
        store.save_scenario("扩容", engine, stats_b)

        report = store.compare("基准", "扩容")
        assert report["scenario_a"]["name"] == "基准"
        assert report["scenario_b"]["name"] == "扩容"

        acc = report["metrics"]["acceptance_rate"]
        assert acc["a"] == pytest.approx(0.8)
        assert acc["b"] == pytest.approx(0.9)
        assert acc["delta"] == pytest.approx(0.1)
        assert acc["delta_pct"] == pytest.approx(12.5)

    def test_compare_summary_positive(self, engine, store):
        stats_a = _mock_stats()
        stats_b = {**_mock_stats(), "decision_metrics": {
            "acceptance_rate": 0.95,
            "completion_rate": 0.98,
            "avg_scheduling_time": 3.0,
            "avg_transmission_time": 90.0,
            "throughput_mbps": 300.0,
        }}
        store.save_scenario("A", engine, stats_a)
        store.save_scenario("B", engine, stats_b)
        report = store.compare("A", "B")
        assert "提升" in report["summary"]

    def test_compare_missing_a(self, engine, store):
        store.save_scenario("存在", engine)
        with pytest.raises(KeyError):
            store.compare("不存在", "存在")

    def test_compare_missing_b(self, engine, store):
        store.save_scenario("存在", engine)
        with pytest.raises(KeyError):
            store.compare("存在", "不存在")

    def test_compare_zero_delta(self, engine, store):
        store.save_scenario("A", engine, _mock_stats())
        store.save_scenario("B", engine, _mock_stats())
        report = store.compare("A", "B")
        # 完全相同的统计，差值应为 0
        assert report["metrics"]["acceptance_rate"]["delta"] == pytest.approx(0.0)
        assert "不显著" in report["summary"]


class TestScenarioStoreSwitchTo:
    def test_switch_to(self, engine, store):
        store.save_scenario("基准", engine)
        result = store.switch_to("基准", engine)
        assert result["restored"] is True

    def test_switch_to_missing(self, engine, store):
        with pytest.raises(KeyError):
            store.switch_to("不存在", engine)


class TestScenarioStoreApi:
    """通过 Flask test_client 测试场景库 API 端点。"""

    @pytest.fixture(autouse=True)
    def setup_client(self, engine):
        import backend.api as api_module
        from backend.store import ScenarioStore

        original_engine = api_module.simulation_engine
        original_store = api_module._scenario_store

        api_module.simulation_engine = engine
        api_module._scenario_store = ScenarioStore(":memory:")
        api_module.app.config["TESTING"] = True

        with api_module.app.test_client() as c:
            self.client = c
            self.store = api_module._scenario_store
            yield

        engine.running = False
        api_module.simulation_engine = original_engine
        api_module._scenario_store = original_store

    def _admin_headers(self):
        import backend.api as api_module
        from backend.auth import create_access_token
        token = create_access_token("admin", "admin")
        return {"Authorization": f"Bearer {token}"}

    def test_list_empty(self):
        resp = self.client.get("/api/scenarios")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"] == []

    def test_save_and_list(self):
        headers = self._admin_headers()
        resp = self.client.post(
            "/api/scenarios",
            json={"name": "测试场景"},
            headers=headers,
        )
        assert resp.status_code == 200

        resp = self.client.get("/api/scenarios")
        body = resp.get_json()
        assert len(body["data"]) == 1
        assert body["data"][0]["name"] == "测试场景"

    def test_delete(self):
        headers = self._admin_headers()
        self.client.post("/api/scenarios", json={"name": "临时"}, headers=headers)
        resp = self.client.delete("/api/scenarios/临时", headers=headers)
        assert resp.status_code == 200
        resp = self.client.get("/api/scenarios")
        assert resp.get_json()["data"] == []

    def test_compare_endpoint(self):
        headers = self._admin_headers()
        self.client.post("/api/scenarios", json={"name": "A"}, headers=headers)
        self.client.post("/api/scenarios", json={"name": "B"}, headers=headers)
        resp = self.client.get("/api/scenario/compare?a=A&b=B")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["scenario_a"]["name"] == "A"
        assert body["data"]["scenario_b"]["name"] == "B"
        assert "metrics" in body["data"]

    def test_compare_missing_params(self):
        resp = self.client.get("/api/scenario/compare?a=A")
        assert resp.status_code == 400

    def test_compare_not_found(self):
        resp = self.client.get("/api/scenario/compare?a=不存在&b=也不存在")
        assert resp.status_code == 404

    def test_save_missing_name(self):
        headers = self._admin_headers()
        resp = self.client.post("/api/scenarios", json={}, headers=headers)
        assert resp.status_code == 400

    def test_set_baseline(self):
        headers = self._admin_headers()
        self.client.post("/api/scenarios", json={"name": "基线场景"}, headers=headers)
        resp = self.client.post("/api/scenarios/基线场景/baseline", headers=headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["baseline"] == "基线场景"

    def test_activate(self):
        headers = self._admin_headers()
        self.client.post("/api/scenarios", json={"name": "可用场景"}, headers=headers)
        resp = self.client.post("/api/scenarios/可用场景/activate", headers=headers)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["data"]["restored"] is True
