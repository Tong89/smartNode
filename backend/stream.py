# -*- coding: utf-8 -*-
"""
SSE (Server-Sent Events) streaming module for SmartNode.

Provides an internal publish/subscribe bus and a Flask response generator
that pushes real-time situation snapshots and scheduling events to clients.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any, Generator, Optional

# Maximum number of pending events per subscriber before oldest are dropped
_QUEUE_MAXSIZE = 128

# How often (seconds) to push a full snapshot even without new events
_SNAPSHOT_INTERVAL = 2.0

# Heartbeat comment interval (keeps proxy connections alive)
_HEARTBEAT_INTERVAL = 15.0


class _EventBus:
    """In-process fan-out message bus for SSE subscribers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[queue.Queue] = []

    def subscribe(self) -> queue.Queue:
        """Register a new subscriber and return its dedicated queue."""
        q: queue.Queue = queue.Queue(maxsize=_QUEUE_MAXSIZE)
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        """Remove a subscriber queue (called when the HTTP connection closes)."""
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass

    def publish(self, event_type: str, data: Any) -> None:
        """
        Publish an event to all active subscribers.

        ``event_type`` should be one of ``"snapshot"`` or ``"event"``.
        ``data`` must be JSON-serialisable.
        """
        payload = json.dumps(data, ensure_ascii=False)
        msg = {"event_type": event_type, "payload": payload}
        with self._lock:
            dead: list[queue.Queue] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(msg)
                except queue.Full:
                    # Subscriber is too slow: drop the oldest item and retry
                    try:
                        q.get_nowait()
                        q.put_nowait(msg)
                    except (queue.Empty, queue.Full):
                        dead.append(q)
            for q in dead:
                try:
                    self._subscribers.remove(q)
                except ValueError:
                    pass


# Module-level singleton – imported by api.py and core.py
event_bus = _EventBus()


# ---------------------------------------------------------------------------
# Snapshot pusher thread
# ---------------------------------------------------------------------------

def _snapshot_loop(engine_ref_getter) -> None:
    """
    Background thread: periodically publishes a full situation snapshot.

    ``engine_ref_getter`` is a zero-argument callable that returns the
    current ``SimulationEngine`` instance so we avoid a circular import.
    """
    last_push = 0.0
    while True:
        now = time.monotonic()
        if now - last_push >= _SNAPSHOT_INTERVAL:
            try:
                engine = engine_ref_getter()
                if engine is not None:
                    snap = _build_snapshot(engine)
                    event_bus.publish("snapshot", snap)
            except Exception:  # noqa: BLE001
                pass  # never crash the background thread
            last_push = time.monotonic()
        time.sleep(0.1)


def _build_snapshot(engine) -> dict:
    """Build a compact situational snapshot from the simulation engine."""
    with engine.lock:
        current_time = engine.current_time
        active = list(engine.transmission_requests)
        stats = engine.stats.copy()
        leo = list(engine.leo_satellites)
        meo = list(engine.meo_satellites)
        geo = list(engine.geo_relays)
        gs = list(engine.ground_stations)

    satellites = []
    for sat in leo:
        pos = engine.get_satellite_position(sat)
        satellites.append({
            "id": sat.sat_id,
            "name": sat.name,
            "type": "LEO",
            "lat": pos["lat"],
            "lon": pos["lon"],
            "alt": pos["alt"],
        })
    for sat in meo:
        pos = engine.get_satellite_position(sat)
        satellites.append({
            "id": sat.sat_id,
            "name": sat.name,
            "type": "MEO",
            "lat": pos["lat"],
            "lon": pos["lon"],
            "alt": pos["alt"],
        })

    geo_data = []
    for relay in geo:
        pos = engine.get_geo_position(relay)
        geo_data.append({
            "id": relay["id"],
            "name": relay["name"],
            "lat": pos["lat"],
            "lon": pos["lon"],
            "alt": pos["alt"],
        })

    requests_data = [r.to_dict() for r in active]

    return {
        "time": current_time,
        "satellites": satellites,
        "ground_stations": [g for g in gs],
        "geo_relays": geo_data,
        "stats": stats,
        "requests": requests_data,
    }


def start_snapshot_thread(engine_ref_getter) -> threading.Thread:
    """
    Launch the background snapshot-push thread (daemon, will not block shutdown).
    """
    t = threading.Thread(
        target=_snapshot_loop,
        args=(engine_ref_getter,),
        daemon=True,
        name="sse-snapshot-pusher",
    )
    t.start()
    return t


# ---------------------------------------------------------------------------
# SSE response generator
# ---------------------------------------------------------------------------

def _format_sse(event_type: str, data: str, event_id: Optional[int] = None) -> str:
    """Format a single SSE frame."""
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_type}")
    # SSE data must be a single line or split across multiple ``data:`` fields
    for line in data.splitlines():
        lines.append(f"data: {line}")
    lines.append("")  # blank line terminates frame
    lines.append("")
    return "\n".join(lines)


def sse_stream(timeout: float = 0) -> Generator[str, None, None]:
    """
    Generator that yields SSE-formatted frames for a single HTTP connection.

    ``timeout`` – if > 0, close the stream after that many seconds (useful
    for tests).  Pass 0 for an indefinite stream.
    """
    q = event_bus.subscribe()
    start = time.monotonic()
    last_heartbeat = start
    event_id = 0

    try:
        while True:
            if timeout > 0 and (time.monotonic() - start) >= timeout:
                break

            # Send a SSE comment heartbeat periodically
            now = time.monotonic()
            if now - last_heartbeat >= _HEARTBEAT_INTERVAL:
                yield ": heartbeat\n\n"
                last_heartbeat = now

            try:
                msg = q.get(timeout=1.0)
            except queue.Empty:
                continue

            event_type = msg["event_type"]
            payload = msg["payload"]
            event_id += 1
            yield _format_sse(event_type, payload, event_id)

    finally:
        event_bus.unsubscribe(q)
