# -*- coding: utf-8 -*-
"""多场景库持久化模块 (store.py)

管理多个命名场景，支持 SQLite 持久化存储，提供以下功能：
- ScenarioStore : 场景库管理器
  * save_scenario(name, engine, stats)  保存或更新一个命名场景（资源配置 + 运行统计快照）
  * load_scenario(name) -> dict | None  按名称加载场景
  * list_scenarios() -> list[dict]      列出全部场景摘要（不含完整统计）
  * delete_scenario(name) -> bool       删除命名场景
  * set_baseline(name) -> bool          将指定场景设为基线
  * get_baseline() -> dict | None       返回当前基线场景
  * compare(name_a, name_b) -> dict     对两个场景的决策指标进行对比，返回差值分析

场景持久化 schema：
{
  "id": int,                     # 自增主键
  "name": str,                   # 场景名称（唯一）
  "version": str,                # 场景版本
  "saved_at": str,               # ISO-8601 时间���
  "is_baseline": bool,           # 是否为基线场景
  "ground_station_count": int,
  "leo_satellite_count": int,
  "geo_relay_count": int,
  "data_types": list[str],
  "run_stats": dict,             # 最近一次运行统计快照（decision_metrics 等）
}
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.scenario import ScenarioManager, SCENARIO_VERSION

# 决策指标维度（用于对比报告）
COMPARE_METRIC_FIELDS = [
    "acceptance_rate",
    "completion_rate",
    "avg_scheduling_time",
    "avg_transmission_time",
    "throughput_mbps",
]

COMPARE_METRIC_LABELS = {
    "acceptance_rate": "接受率",
    "completion_rate": "完成率",
    "avg_scheduling_time": "平均调度时延(s)",
    "avg_transmission_time": "平均传输时延(s)",
    "throughput_mbps": "吞吐量(Mbps)",
}


class ScenarioStore:
    """场景库管理器——多场景持久化、切换与对比。

    Parameters
    ----------
    db_path:
        SQLite 数据库路径，默认内存数据库（进程重启后丢失）。
        生产环境可传入文件路径以持久化。
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    # ── 数据库初始化 ──────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        """创建场景库表（幂等）。"""
        with self._lock, self._conn:
            self._conn.execute(
                """CREATE TABLE IF NOT EXISTS scenarios (
                       id          INTEGER PRIMARY KEY AUTOINCREMENT,
                       name        TEXT UNIQUE NOT NULL,
                       version     TEXT NOT NULL DEFAULT '1',
                       saved_at    TEXT NOT NULL,
                       is_baseline INTEGER NOT NULL DEFAULT 0,
                       gs_count    INTEGER NOT NULL DEFAULT 0,
                       leo_count   INTEGER NOT NULL DEFAULT 0,
                       geo_count   INTEGER NOT NULL DEFAULT 0,
                       data_types  TEXT NOT NULL DEFAULT '[]',
                       run_stats   TEXT NOT NULL DEFAULT '{}'
                   )"""
            )
            # 迁移：旧版本可能没有 geo_count 列
            try:
                self._conn.execute("ALTER TABLE scenarios ADD COLUMN geo_count INTEGER NOT NULL DEFAULT 0")
            except sqlite3.OperationalError:
                pass  # 列已存在，忽略

    # ── 内部帮助函数 ──────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        """将 sqlite3.Row 转换为带类型解码的 dict。"""
        d = dict(row)
        d["is_baseline"] = bool(d.get("is_baseline", 0))
        try:
            d["data_types"] = json.loads(d.get("data_types") or "[]")
        except (json.JSONDecodeError, TypeError):
            d["data_types"] = []
        try:
            d["run_stats"] = json.loads(d.get("run_stats") or "{}")
        except (json.JSONDecodeError, TypeError):
            d["run_stats"] = {}
        return d

    # ── 公共接口 ──────────────────────────────────────────────────────────────

    def save_scenario(
        self,
        name: str,
        engine: Any,
        stats: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """保存（或更新）一个命名场景。

        Parameters
        ----------
        name:
            场景名称（<=128 字符，全库唯一）。
        engine:
            ``SimulationEngine`` 实例——用于提取资源配置。
        stats:
            运行统计快照（通常为 ``engine.get_stats()``）；
            未传入时仅保存资源配置，run_stats 置空。

        Returns
        -------
        dict
            保存后的完整场景记录。
        """
        name = str(name)[:128].strip()
        if not name:
            raise ValueError("场景名称不可为空")

        scene = ScenarioManager.save(engine, name=name)
        run_stats: Dict[str, Any] = {}
        if stats is not None:
            # 仅保留决策指标与请求统计，避免写入大型原始数据
            run_stats = {
                "total_requests": stats.get("total_requests", 0),
                "accepted_requests": stats.get("accepted_requests", 0),
                "rejected_requests": stats.get("rejected_requests", 0),
                "completed_requests": stats.get("completed_requests", 0),
                "decision_metrics": stats.get("decision_metrics", {}),
                "rejection_distribution": stats.get("rejection_distribution", {}),
            }

        saved_at = datetime.now(tz=timezone.utc).isoformat()
        data_types_json = json.dumps(scene.get("data_types", []), ensure_ascii=False)
        run_stats_json = json.dumps(run_stats, ensure_ascii=False)

        with self._lock, self._conn:
            self._conn.execute(
                """INSERT INTO scenarios
                       (name, version, saved_at, is_baseline, gs_count, leo_count, geo_count, data_types, run_stats)
                   VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                       version=excluded.version,
                       saved_at=excluded.saved_at,
                       gs_count=excluded.gs_count,
                       leo_count=excluded.leo_count,
                       geo_count=excluded.geo_count,
                       data_types=excluded.data_types,
                       run_stats=excluded.run_stats""",
                (
                    name,
                    SCENARIO_VERSION,
                    saved_at,
                    scene.get("ground_station_count", 0),
                    scene.get("leo_satellite_count", 0),
                    scene.get("geo_relay_count", 0),
                    data_types_json,
                    run_stats_json,
                ),
            )

        return self.load_scenario(name) or {}

    def load_scenario(self, name: str) -> Optional[Dict[str, Any]]:
        """按名称加载完整场景记录。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM scenarios WHERE name=?", (name,)
            ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def list_scenarios(self) -> List[Dict[str, Any]]:
        """列出全部场景摘要（不含 run_stats 详情以减小响应体积）。

        Returns
        -------
        list[dict]
            按 saved_at 倒序排列的摘要列表，每条包含
            id / name / saved_at / is_baseline / gs_count / leo_count / geo_count。
        """
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, name, version, saved_at, is_baseline,
                          gs_count, leo_count, geo_count
                   FROM scenarios
                   ORDER BY saved_at DESC"""
            ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["is_baseline"] = bool(d.get("is_baseline", 0))
            result.append(d)
        return result

    def delete_scenario(self, name: str) -> bool:
        """删除指定场景，返回是否成功（False 表示场景不存在）。"""
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM scenarios WHERE name=?", (name,))
        return cur.rowcount > 0

    def set_baseline(self, name: str) -> bool:
        """将指定场景设为基线，同时取消之前的基线标记。

        Returns
        -------
        bool
            True 表示成功（场景存在），False 表示场景不存在。
        """
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM scenarios WHERE name=?", (name,)
            ).fetchone()
            if exists is None:
                return False
            with self._conn:
                self._conn.execute("UPDATE scenarios SET is_baseline=0")
                self._conn.execute(
                    "UPDATE scenarios SET is_baseline=1 WHERE name=?", (name,)
                )
        return True

    def get_baseline(self) -> Optional[Dict[str, Any]]:
        """返回当前基线场景（完整记录），若无基线返回 None。"""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM scenarios WHERE is_baseline=1 LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    def switch_to(self, name: str, engine: Any) -> Dict[str, Any]:
        """将引擎资源配置切换为指定场景。

        Parameters
        ----------
        name:
            目标场景名称。
        engine:
            ``SimulationEngine`` 实例。

        Returns
        -------
        dict
            ``ScenarioManager.load`` 的还原结果摘要。

        Raises
        ------
        KeyError
            场景不存在时抛出。
        ValueError
            场景数据非法时抛出。
        """
        record = self.load_scenario(name)
        if record is None:
            raise KeyError(f"场景 '{name}' 不存在")

        # 重建符合 ScenarioManager.load 期望的 schema dict
        scene_dict = {
            "version": record.get("version", SCENARIO_VERSION),
            "name": record["name"],
            "saved_at": record.get("saved_at", ""),
            "ground_station_count": record.get("gs_count", 0),
            "leo_satellite_count": record.get("leo_count", 0),
            "geo_relay_count": record.get("geo_count", 0),
            "data_types": record.get("data_types", []),
        }
        return ScenarioManager.load(engine, scene_dict)

    def compare(self, name_a: str, name_b: str) -> Dict[str, Any]:
        """对两个场景的决策指标进行对比，返回差值分析报告。

        Parameters
        ----------
        name_a:
            场景 A 的名称（通常为基线）。
        name_b:
            场景 B 的名称（通常为待对比场景）。

        Returns
        -------
        dict
            ::

                {
                  "scenario_a": {"name": ..., "saved_at": ...},
                  "scenario_b": {"name": ..., "saved_at": ...},
                  "resource_diff": {
                      "gs_count": {"a": int, "b": int, "delta": int},
                      "leo_count": {"a": int, "b": int, "delta": int},
                  },
                  "metrics": {
                      "<field>": {
                          "label": str,
                          "a": float, "b": float,
                          "delta": float,           # b - a
                          "delta_pct": float | None # (b-a)/a*100, None if a==0
                      },
                      ...
                  },
                  "summary": str  # 人类可读的简短结论
                }

        Raises
        ------
        KeyError
            任一场景不存在时抛出。
        """
        rec_a = self.load_scenario(name_a)
        rec_b = self.load_scenario(name_b)
        if rec_a is None:
            raise KeyError(f"场景 '{name_a}' 不存在")
        if rec_b is None:
            raise KeyError(f"场景 '{name_b}' 不存在")

        metrics_a = rec_a.get("run_stats", {}).get("decision_metrics", {})
        metrics_b = rec_b.get("run_stats", {}).get("decision_metrics", {})

        # 逐指标计算差值
        metrics_report: Dict[str, Any] = {}
        for field in COMPARE_METRIC_FIELDS:
            val_a = float(metrics_a.get(field, 0.0))
            val_b = float(metrics_b.get(field, 0.0))
            delta = round(val_b - val_a, 6)
            delta_pct: Optional[float] = None
            if val_a != 0.0:
                delta_pct = round((val_b - val_a) / abs(val_a) * 100, 2)
            metrics_report[field] = {
                "label": COMPARE_METRIC_LABELS.get(field, field),
                "a": round(val_a, 6),
                "b": round(val_b, 6),
                "delta": delta,
                "delta_pct": delta_pct,
            }

        # 资源配置差异
        resource_diff = {
            "gs_count": {
                "label": "地面站数",
                "a": rec_a.get("gs_count", 0),
                "b": rec_b.get("gs_count", 0),
                "delta": rec_b.get("gs_count", 0) - rec_a.get("gs_count", 0),
            },
            "leo_count": {
                "label": "LEO卫星数",
                "a": rec_a.get("leo_count", 0),
                "b": rec_b.get("leo_count", 0),
                "delta": rec_b.get("leo_count", 0) - rec_a.get("leo_count", 0),
            },
        }

        # 生成简短文字结论
        acc_delta = metrics_report.get("acceptance_rate", {}).get("delta", 0.0)
        thr_delta = metrics_report.get("throughput_mbps", {}).get("delta", 0.0)
        if acc_delta > 0.01 or thr_delta > 0.5:
            summary = f"场景 '{name_b}' 相对 '{name_a}' 整体性能提升"
        elif acc_delta < -0.01 or thr_delta < -0.5:
            summary = f"场景 '{name_b}' 相对 '{name_a}' 整体性能下降"
        else:
            summary = f"场景 '{name_a}' 与 '{name_b}' 指标相近，差异不显著"

        return {
            "scenario_a": {
                "name": rec_a["name"],
                "saved_at": rec_a.get("saved_at", ""),
                "is_baseline": rec_a.get("is_baseline", False),
            },
            "scenario_b": {
                "name": rec_b["name"],
                "saved_at": rec_b.get("saved_at", ""),
                "is_baseline": rec_b.get("is_baseline", False),
            },
            "resource_diff": resource_diff,
            "metrics": metrics_report,
            "summary": summary,
        }

    def close(self) -> None:
        """关闭数据库连接。"""
        self._conn.close()
