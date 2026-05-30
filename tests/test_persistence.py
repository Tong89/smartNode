import os, sys, tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.persistence.db import SqliteRepository

def test_save_load_requests_and_upsert():
    f = os.path.join(tempfile.mkdtemp(), "t.db")
    repo = SqliteRepository(f)
    repo.save_request({"id": "REQ_0001", "data_type": "TASK_CMD", "status": "accepted", "submit_time": 1.0})
    repo.save_request({"id": "REQ_0001", "data_type": "TASK_CMD", "status": "completed", "complete_time": 5.0, "submit_time": 1.0})
    repo.save_request({"id": "REQ_0002", "data_type": "INTEL", "status": "rejected", "submit_time": 2.0})
    repo.close()
    # reopen -> survives restart
    repo2 = SqliteRepository(f)
    reqs = repo2.load_requests()
    assert repo2.count_requests() == 2  # upsert, no dup
    assert reqs[0]["id"] == "REQ_0001" and reqs[0]["status"] == "completed"

def test_stats_snapshot():
    repo = SqliteRepository(":memory:")
    assert repo.load_latest_stats() is None
    repo.save_stats_snapshot({"total_requests": 10})
    repo.save_stats_snapshot({"total_requests": 20})
    assert repo.load_latest_stats()["total_requests"] == 20
