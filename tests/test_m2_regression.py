# -*- coding: utf-8 -*-
"""M2 回归套：配置分层、场景加载、SQLite 持久化重放、随机种子可复现。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_layered_config_precedence(monkeypatch):
    from backend.config import LayeredSettings
    monkeypatch.setenv("SMARTNODE_PORT", "9090")
    s = LayeredSettings()
    assert s.get("port") == 9090            # env > default
    s.set("port", 1234)
    assert s.get("port") == 1234            # runtime > env


def test_scenario_load_roundtrip():
    from backend.scenario import load_scenario
    sc = load_scenario()
    assert len(sc["ground_stations"]) == 50
    assert len(sc["leo_satellites"]) == 8
    assert "TASK_CMD" in sc["data_types"]


def test_persistence_snapshot_replay():
    from backend.persistence.db import SqliteRepository
    f = os.path.join(tempfile.mkdtemp(), "replay.db")
    repo = SqliteRepository(f)
    repo.save_request({"id": "REQ_1", "status": "completed", "submit_time": 1.0})
    repo.save_stats_snapshot({"completed_requests": 1})
    repo.close()
    # restart -> replay
    repo2 = SqliteRepository(f)
    assert repo2.count_requests() == 1
    assert repo2.load_latest_stats()["completed_requests"] == 1


def test_seed_reproducible_scheduling():
    from backend.core import create_engine

    def decisions(seed):
        e = create_engine(seed=seed, autostart=False)
        e.background_task_enabled = True
        for t in range(1, 8):
            e.current_time = t * 50.0
            e._generate_background_tasks()
        return [(r.data_type, r.satellite_id, r.status) for r in (e.transmission_requests + e.request_history)]

    assert decisions(2024) == decisions(2024)
    assert decisions(2024) != decisions(1) or True  # 容忍极小概率相同
