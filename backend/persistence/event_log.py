# -*- coding: utf-8 -*-
"""请求生命周期事件日志（append-only，JSON Lines）。

记录提交/接受/开始传输/链路切换/完成/拒绝等事件，便于审计与回放重建。仅追加写，不修改历史。
内存模式（path=None）便于测试；文件模式逐行追加 JSON。
"""
import json
import threading
import time

# 事件类型常量
SUBMITTED = "submitted"
ACCEPTED = "accepted"
REJECTED = "rejected"
TRANSMIT_START = "transmit_start"
HANDOVER = "handover"
COMPLETED = "completed"
INTERRUPTED = "interrupted"


class EventLog:
    def __init__(self, path=None):
        self.path = path
        self._lock = threading.Lock()
        self._buffer = []  # 内存镜像（便于查询/测试）

    def append(self, event_type, request_id=None, **fields):
        record = {"ts": time.time(), "type": event_type, "request_id": request_id}
        record.update(fields)
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            self._buffer.append(record)
            if self.path:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        return record

    def events(self, request_id=None, event_type=None):
        with self._lock:
            items = list(self._buffer)
        if request_id is not None:
            items = [e for e in items if e.get("request_id") == request_id]
        if event_type is not None:
            items = [e for e in items if e.get("type") == event_type]
        return items

    def trim(self, max_events):
        """仅保留最近 max_events 条事件（内存与文件同步），控制存储增长。"""
        with self._lock:
            self._buffer = self._buffer[-max_events:]
            if self.path:
                with open(self.path, "w", encoding="utf-8") as f:
                    for rec in self._buffer:
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return len(self._buffer)

    @staticmethod
    def read_file(path):
        out = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        out.append(json.loads(line))
        except OSError:
            pass
        return out
