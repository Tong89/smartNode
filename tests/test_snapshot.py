# -*- coding: utf-8 -*-
"""仿真快照（Snapshot）功能测试。

覆盖：
1. SnapshotManager.take()    — 快照内容完整性
2. SnapshotManager.restore() — 态势数据回到快照时刻，无字段缺失
3. SnapshotManager.validate()— 非法快照的错误检测
4. SnapshotManager.to_json() / from_json() — 序列化往返
5. SimulationEngine.snapshot() / restore() / resume_from_snapshot() — 引擎方法集成
6. 回放模式（replay_mode）下主循环暂停验证
7. Flask API /api/snapshot/* 端点的集成测试
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from backend.core import SimulationEngine, TransmissionRequest, create_engine
from backend.snapshot import SnapshotManager, SNAPSHOT_VERSION


# ─────────────────────────────────────────────────────────────────────────────
# 辅助函数
# ─────────────────────────────────────────────────────────────────────────────

def _make_engine():
    """创建一个固定种子、不启动后台线程的引擎。"""
    TransmissionRequest._id_counter = 0
    return create_engine(seed=1, autostart=False)


def _advance(engine, delta: float = 100.0):
    """手动推进仿真时钟（不启动线程时需要手动推进）。"""
    with engine.lock:
        engine.current_time += delta


def _inject_request(engine):
    """直接向引擎历史队列注入一条已完成的请求（不触发真实提交流程）。"""
    req = TransmissionRequest(
        data_type="DATA_SLICE",
        data_size=10,
        priority=5,
        max_delay=1800,
    )
    req.submit_time = engine.current_time
    req.status = "completed"
    req.progress = 100.0
    with engine.lock:
        engine.request_history.append(req)
        engine.stats["total_requests"] += 1
        engine.stats["completed_requests"] += 1
    return req


# ─────────────────────────────────────────────────────────────────────────────
# 1. SnapshotManager.take — 快照内容完整性
# ─────────────────────────────────────────────────────────────────────────────

class TestSnapshotTake:
    def test_snapshot_schema_fields(self):
        """拍摄快照后，必填字段全部存在。"""
        eng = _make_engine()
        snap = SnapshotManager.take(eng, label="test-label")

        assert snap["version"] == SNAPSHOT_VERSION
        assert "saved_at" in snap
        assert snap["label"] == "test-label"
        assert isinstance(snap["current_time"], float)
        assert "id_counter" in snap
        assert isinstance(snap["transmission_requests"], list)
        assert isinstance(snap["request_history"], list)
        assert "resource_usage" in snap
        assert "stats" in snap

    def test_snapshot_captures_current_time(self):
        """快照记录的仿真时钟与引擎一致。"""
        eng = _make_engine()
        _advance(eng, 500.0)
        snap = SnapshotManager.take(eng)
        assert snap["current_time"] == pytest.approx(500.0)

    def test_snapshot_captures_requests(self):
        """快照包含已注入的历史请求。"""
        eng = _make_engine()
        _advance(eng)
        _inject_request(eng)
        snap = SnapshotManager.take(eng)
        total = len(snap["transmission_requests"]) + len(snap["request_history"])
        assert total >= 1

    def test_snapshot_engine_method(self):
        """SimulationEngine.snapshot() 等价于 SnapshotManager.take()。"""
        eng = _make_engine()
        snap = eng.snapshot(label="via-engine")
        assert snap["version"] == SNAPSHOT_VERSION
        assert snap["label"] == "via-engine"

    def test_snapshot_id_counter(self):
        """快照记录拍摄时的 ID 计数器值。"""
        eng = _make_engine()
        _advance(eng)
        _inject_request(eng)
        _inject_request(eng)
        snap = SnapshotManager.take(eng)
        # id_counter 在注入时由 TransmissionRequest.__init__ 自增
        assert snap["id_counter"] >= 2

    def test_snapshot_resource_usage_structure(self):
        """快照中 resource_usage 包含三类资源键。"""
        eng = _make_engine()
        snap = SnapshotManager.take(eng)
        ru = snap["resource_usage"]
        assert "satellites" in ru
        assert "ground_stations" in ru
        assert "geo_relays" in ru

    def test_snapshot_stats_keys(self):
        """快照中 stats 包含 total_requests 等基础字段。"""
        eng = _make_engine()
        _advance(eng)
        _inject_request(eng)
        snap = SnapshotManager.take(eng)
        assert "total_requests" in snap["stats"]
        assert "completed_requests" in snap["stats"]


# ─────────────────────────────────────────────────────────────────────────────
# 2. SnapshotManager.restore — 态势回到快照时刻
# ─────────────────────────────────────────────────────────────────────────────

class TestSnapshotRestore:
    def test_restore_current_time(self):
        """恢复后引擎时钟等于快照时钟。"""
        eng = _make_engine()
        _advance(eng, 300.0)
        snap = SnapshotManager.take(eng)

        # 继续推进
        _advance(eng, 200.0)
        assert eng.current_time == pytest.approx(500.0)

        # 恢复
        SnapshotManager.restore(eng, snap)
        assert eng.current_time == pytest.approx(300.0)

    def test_restore_enters_replay_mode(self):
        """恢复后引擎进入回放模式（running=False, _replay_mode=True）。"""
        eng = _make_engine()
        snap = SnapshotManager.take(eng)
        result = SnapshotManager.restore(eng, snap)

        assert eng.running is False
        assert getattr(eng, "_replay_mode", False) is True
        assert result["replay_mode"] is True

    def test_restore_result_fields(self):
        """restore() 返回摘要字典包含必要字段。"""
        eng = _make_engine()
        snap = SnapshotManager.take(eng, label="chk")
        result = SnapshotManager.restore(eng, snap)

        assert result["restored"] is True
        assert "restored_time" in result
        assert "request_count" in result
        assert "history_count" in result
        assert result["label"] == "chk"

    def test_restore_requests_match_snapshot(self):
        """恢复后请求列表与快照一致（通过注入方式）。"""
        eng = _make_engine()
        _advance(eng)
        _inject_request(eng)
        snap = SnapshotManager.take(eng)

        # 注入更多请求，改变引擎状态
        _inject_request(eng)
        _inject_request(eng)

        # 恢复
        SnapshotManager.restore(eng, snap)

        snap_total = len(snap["transmission_requests"]) + len(snap["request_history"])
        eng_total = len(eng.transmission_requests) + len(eng.request_history)
        assert eng_total == snap_total

    def test_restore_stats_match_snapshot(self):
        """恢复后统计字段（total_requests 等）与快照一致。"""
        eng = _make_engine()
        _advance(eng)
        _inject_request(eng)
        snap = SnapshotManager.take(eng)

        # 注入更多请求，改变 stats
        _inject_request(eng)
        assert eng.stats["total_requests"] > snap["stats"]["total_requests"]

        # 恢复
        SnapshotManager.restore(eng, snap)
        assert eng.stats["total_requests"] == snap["stats"]["total_requests"]

    def test_engine_restore_method(self):
        """SimulationEngine.restore() 等价于 SnapshotManager.restore()。"""
        eng = _make_engine()
        _advance(eng, 100.0)
        snap = eng.snapshot()
        _advance(eng, 50.0)

        result = eng.restore(snap)
        assert result["restored"] is True
        assert eng.current_time == pytest.approx(100.0)

    def test_restore_invalid_snapshot_raises(self):
        """传入非法快照时 restore() 抛出 ValueError。"""
        eng = _make_engine()
        with pytest.raises(ValueError):
            SnapshotManager.restore(eng, {"version": "99", "current_time": 0})

    def test_restore_without_active_requests(self):
        """空请求状态也能完整恢复（无字段缺失）。"""
        eng = _make_engine()
        snap = SnapshotManager.take(eng)
        result = SnapshotManager.restore(eng, snap)
        assert result["request_count"] == 0
        assert result["history_count"] == 0

    def test_restore_request_ids_preserved(self):
        """恢复后请求 ID 与快照时保持一致。"""
        eng = _make_engine()
        req = _inject_request(eng)
        original_id = req.id
        snap = SnapshotManager.take(eng)

        # 清空并恢复
        with eng.lock:
            eng.request_history.clear()
        SnapshotManager.restore(eng, snap)

        restored_ids = [r.id for r in eng.request_history]
        assert original_id in restored_ids


# ─────────────────────────────────────────────────────────────────────────────
# 3. 回放模式与恢复
# ─────────────────────────────────────────────────────────────────────────────

class TestReplayMode:
    def test_resume_from_snapshot_restarts_loop(self):
        """resume_from_snapshot() 退出回放模式，running 标志变为 True。"""
        eng = _make_engine()
        snap = SnapshotManager.take(eng)
        SnapshotManager.restore(eng, snap)
        assert eng.running is False

        restarted = eng.resume_from_snapshot()
        assert restarted is True
        assert eng.running is True

        # 清理后台线程
        eng.running = False

    def test_resume_when_already_running_returns_false(self):
        """引擎已在运行时，resume_from_snapshot() 返回 False。"""
        eng = _make_engine()
        eng.running = True
        assert eng.resume_from_snapshot() is False
        eng.running = False

    def test_replay_mode_flag_cleared_after_resume(self):
        """resume 后 _replay_mode 标志被清除。"""
        eng = _make_engine()
        snap = SnapshotManager.take(eng)
        SnapshotManager.restore(eng, snap)
        eng.resume_from_snapshot()
        assert getattr(eng, "_replay_mode", False) is False
        eng.running = False


# ─────────────────────────────────────────────────────────────────────────────
# 4. SnapshotManager.validate — 非法快照检测
# ──────��──────────────────────────────────────────────────────────────────────

class TestSnapshotValidate:
    def test_valid_snapshot_no_errors(self):
        eng = _make_engine()
        snap = SnapshotManager.take(eng)
        errors = SnapshotManager.validate(snap)
        assert errors == []

    def test_missing_version(self):
        snap = {"current_time": 100.0}
        errors = SnapshotManager.validate(snap)
        assert any("version" in e for e in errors)

    def test_wrong_version(self):
        snap = {"version": "99", "current_time": 100.0}
        errors = SnapshotManager.validate(snap)
        assert any("版本" in e or "version" in e.lower() for e in errors)

    def test_missing_current_time(self):
        snap = {"version": SNAPSHOT_VERSION}
        errors = SnapshotManager.validate(snap)
        assert any("current_time" in e for e in errors)

    def test_non_dict_input(self):
        errors = SnapshotManager.validate("not a dict")
        assert len(errors) > 0

    def test_invalid_current_time_type(self):
        snap = {"version": SNAPSHOT_VERSION, "current_time": "abc"}
        errors = SnapshotManager.validate(snap)
        assert any("current_time" in e for e in errors)

    def test_invalid_transmission_requests_type(self):
        snap = {"version": SNAPSHOT_VERSION, "current_time": 0.0, "transmission_requests": "bad"}
        errors = SnapshotManager.validate(snap)
        assert any("transmission_requests" in e for e in errors)


# ─��───────────────────────────────────────────────────────────────────────────
# 5. 序列化往返 (to_json / from_json)
# ─────────────────────────────────────────────────────────────────────────────

class TestSnapshotSerialization:
    def test_json_roundtrip_preserves_fields(self):
        """to_json → from_json 后字段完整保留。"""
        eng = _make_engine()
        _advance(eng, 123.4)
        snap = SnapshotManager.take(eng, label="roundtrip")

        text = SnapshotManager.to_json(snap)
        recovered = SnapshotManager.from_json(text)

        assert recovered["version"] == snap["version"]
        assert recovered["current_time"] == pytest.approx(snap["current_time"])
        assert recovered["label"] == snap["label"]
        assert recovered["id_counter"] == snap["id_counter"]

    def test_from_json_invalid_raises(self):
        with pytest.raises(ValueError):
            SnapshotManager.from_json("not-json{{")

    def test_from_json_non_dict_raises(self):
        with pytest.raises(ValueError):
            SnapshotManager.from_json("[1, 2, 3]")

    def test_serialized_snapshot_passes_validate(self):
        """JSON 往返后快照通过 validate()。"""
        eng = _make_engine()
        snap = SnapshotManager.take(eng)
        text = SnapshotManager.to_json(snap)
        recovered = SnapshotManager.from_json(text)
        assert SnapshotManager.validate(recovered) == []

    def test_restored_from_json_roundtrip(self):
        """JSON 往返后可成功 restore 到引擎。"""
        eng = _make_engine()
        _advance(eng, 400.0)
        snap = SnapshotManager.take(eng)
        text = SnapshotManager.to_json(snap)
        recovered = SnapshotManager.from_json(text)

        _advance(eng, 100.0)
        result = SnapshotManager.restore(eng, recovered)
        assert result["restored"] is True
        assert eng.current_time == pytest.approx(400.0)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Flask API 端点集成测试
# ─────────────────────────────────────────────────────────────────────────────

class TestSnapshotAPI:
    """通过 Flask test_client 测试 /api/snapshot/* 端点。"""

    @pytest.fixture(autouse=True)
    def reset_snapshot(self):
        """每个测试前后重置 api 模块的 _saved_snapshot。"""
        import backend.api as api_module
        api_module._saved_snapshot = None
        yield
        api_module._saved_snapshot = None

    def test_snapshot_status_no_snapshot(self, flask_client_engine):
        """无快照时 /api/snapshot/status 返回 available=False。"""
        client, eng = flask_client_engine
        resp = client.get("/api/snapshot/status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["code"] == 0
        assert data["data"]["snapshot"]["available"] is False

    def test_snapshot_save_returns_summary(self, flask_client_engine):
        """POST /api/snapshot/save 返回快照摘要。"""
        client, eng = flask_client_engine
        resp = client.post(
            "/api/snapshot/save",
            json={"label": "api-test"},
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["code"] == 0
        summary = data["data"]
        assert summary["version"] == SNAPSHOT_VERSION
        assert summary["label"] == "api-test"
        assert "current_time" in summary
        assert "active_request_count" in summary

    def test_snapshot_load_without_save_returns_404(self, flask_client_engine):
        """未保存快照时 POST /api/snapshot/load 返回 NOT_FOUND。"""
        client, eng = flask_client_engine
        resp = client.post("/api/snapshot/load")
        assert resp.status_code == 404

    def test_snapshot_save_then_load(self, flask_client_engine):
        """保存快照后立即加载，时钟恢复到快照时刻。"""
        client, eng = flask_client_engine
        # 设置引擎时钟
        with eng.lock:
            eng.current_time = 999.0

        # 保存快照
        resp = client.post("/api/snapshot/save", json={"label": "t999"})
        assert resp.status_code == 200

        # 推进时钟
        with eng.lock:
            eng.current_time = 1500.0

        # 加载快照
        resp = client.post("/api/snapshot/load")
        assert resp.status_code == 200
        result = resp.get_json()
        assert result["code"] == 0
        assert result["data"]["restored_time"] == pytest.approx(999.0)

        # 回放模式下主循环应已暂停
        assert eng.running is False

    def test_snapshot_resume_after_load(self, flask_client_engine):
        """加载快照后调用 /api/snapshot/resume 可重启仿真。"""
        client, eng = flask_client_engine
        # 保存 + 加载快照（进入回放模式）
        client.post("/api/snapshot/save")
        client.post("/api/snapshot/load")
        assert eng.running is False

        # 恢复
        resp = client.post("/api/snapshot/resume")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["code"] == 0
        assert data["data"]["restarted"] is True

        # 清理后台线程
        eng.running = False

    def test_snapshot_status_after_save(self, flask_client_engine):
        """保存快照后 status 接口显示 available=True。"""
        client, eng = flask_client_engine
        client.post("/api/snapshot/save", json={"label": "status-test"})
        resp = client.get("/api/snapshot/status")
        data = resp.get_json()
        assert data["code"] == 0
        assert data["data"]["snapshot"]["available"] is True
        assert data["data"]["snapshot"]["label"] == "status-test"

    def test_snapshot_export_returns_json(self, flask_client_engine):
        """GET /api/snapshot/export 返回 JSON 文件内容。"""
        client, eng = flask_client_engine
        client.post("/api/snapshot/save", json={"label": "export-test"})
        resp = client.get("/api/snapshot/export")
        assert resp.status_code == 200
        assert "application/json" in resp.content_type
        body = json.loads(resp.data)
        assert body["version"] == SNAPSHOT_VERSION

    def test_snapshot_export_without_save_returns_404(self, flask_client_engine):
        """未保存快照时 /api/snapshot/export 返回 404。"""
        client, eng = flask_client_engine
        resp = client.get("/api/snapshot/export")
        assert resp.status_code == 404

    def test_snapshot_import_and_restore(self, flask_client_engine):
        """从 JSON 导入快照并恢复仿真状态。"""
        client, eng = flask_client_engine
        with eng.lock:
            eng.current_time = 777.0

        # 生成快照 JSON
        snap = eng.snapshot(label="import-test")
        snap_json = SnapshotManager.to_json(snap)

        # 推进时钟
        with eng.lock:
            eng.current_time = 2000.0

        # 导入快照
        resp = client.post(
            "/api/snapshot/import",
            data=snap_json,
            content_type="application/json",
        )
        assert resp.status_code == 200
        result = resp.get_json()
        assert result["code"] == 0
        assert result["data"]["restored_time"] == pytest.approx(777.0)

    def test_snapshot_import_invalid_json_returns_error(self, flask_client_engine):
        """导入非法 JSON 时返回 VALIDATION_ERROR（HTTP 400）。"""
        client, eng = flask_client_engine
        resp = client.post(
            "/api/snapshot/import",
            data="THIS IS NOT JSON",
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_snapshot_save_with_injected_request(self, flask_client_engine):
        """有历史请求时快照 history_count 正确。"""
        client, eng = flask_client_engine
        # 注入一条历史请求
        _inject_request(eng)
        resp = client.post("/api/snapshot/save")
        assert resp.status_code == 200
        summary = resp.get_json()["data"]
        # 历史数量应 >= 1
        assert summary["history_count"] >= 1
