import os, sys, tempfile
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.persistence.event_log import EventLog, SUBMITTED, COMPLETED

def test_append_only_and_query():
    log = EventLog()
    log.append(SUBMITTED, "REQ_0001", data_type="TASK_CMD")
    log.append(COMPLETED, "REQ_0001", rate=120.0)
    log.append(SUBMITTED, "REQ_0002")
    assert len(log.events()) == 3
    assert len(log.events(request_id="REQ_0001")) == 2
    assert len(log.events(event_type=SUBMITTED)) == 2

def test_file_append_and_read():
    f = os.path.join(tempfile.mkdtemp(), "events.jsonl")
    log = EventLog(f)
    log.append(SUBMITTED, "REQ_0001")
    log.append(COMPLETED, "REQ_0001")
    rows = EventLog.read_file(f)
    assert len(rows) == 2 and rows[0]["type"] == SUBMITTED and rows[1]["type"] == COMPLETED
