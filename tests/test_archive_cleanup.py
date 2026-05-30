import os, sys, tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.persistence.db import SqliteRepository
from backend.persistence.event_log import EventLog, SUBMITTED

def test_purge_and_keep_last():
    repo = SqliteRepository(":memory:")
    for i in range(10):
        repo.save_request({"id": f"R{i}", "status": "completed", "submit_time": float(i)})
    assert repo.purge_requests_before(3.0) == 3      # R0,R1,R2 removed
    assert repo.count_requests() == 7
    assert repo.keep_last_requests(2) == 5           # keep latest 2
    assert repo.count_requests() == 2

def test_event_log_trim():
    f = os.path.join(tempfile.mkdtemp(), "e.jsonl")
    log = EventLog(f)
    for i in range(20):
        log.append(SUBMITTED, f"R{i}")
    assert log.trim(5) == 5
    assert len(log.events()) == 5
    assert len(EventLog.read_file(f)) == 5
