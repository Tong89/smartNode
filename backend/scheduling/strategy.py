# -*- coding: utf-8 -*-
"""可插拔调度策略接口 SchedulingStrategy。

策略输入资源/星座/几何上下文（经 Scheduler 暴露），输出链路决策 dict 或 None。
默认提供贪心最大速率策略；可替换以试验不同选路算法。
"""
from abc import ABC, abstractmethod


class SchedulingStrategy(ABC):
    name = "abstract"

    @abstractmethod
    def select(self, scheduler, req, satellite, sat_pos):
        """返回 {method, ground_station, relay, relay2, rate} 或 None。"""
        raise NotImplementedError


class GreedyMaxRateStrategy(SchedulingStrategy):
    """贪心：在允许的链路中选择可用且速率最高者（与历史行为一致）。"""

    name = "greedy_max_rate"

    def select(self, scheduler, req, satellite, sat_pos):
        from backend.core import DATA_TYPES
        eng = scheduler.engine
        data_config = DATA_TYPES.get(req.data_type, {})
        allowed_links = data_config.get("allowed_links", ["direct"])
        is_immediate_type = req.data_type in ["TASK_CMD", "INTEL"]
        best_link = None
        best_rate = 0

        def can_use_satellite():
            return is_immediate_type or not scheduler.resource_busy_by_other("satellites", satellite.sat_id, req.id)

        def can_use_ground_station(gs_id):
            return is_immediate_type or not scheduler.resource_busy_by_other("ground_stations", gs_id, req.id)

        if "direct" in allowed_links and can_use_satellite():
            for gs in scheduler.ground_station_candidates(req):
                if can_use_ground_station(gs["id"]) and eng.check_visibility(sat_pos, gs, min_elevation=10):
                    rate = eng._calculate_direct_rate(sat_pos, gs, req.data_type)
                    if rate > best_rate:
                        best_rate = rate
                        best_link = {"method": "direct", "ground_station": gs["id"], "relay": None, "relay2": None, "rate": rate}

        if "relay" in allowed_links and can_use_satellite():
            for geo in eng.geo_relays:
                geo_pos = eng.get_geo_position(geo)
                if not eng.check_geo_visibility(sat_pos, geo_pos):
                    continue
                for gs in scheduler.ground_station_candidates(req):
                    if not can_use_ground_station(gs["id"]):
                        continue
                    if not eng.check_visibility(geo_pos, gs, min_elevation=5):
                        continue
                    rate = eng._calculate_relay_rate(sat_pos, geo_pos, gs, req.data_type)
                    if rate > best_rate and scheduler.relay_can_carry_request(geo["id"], rate, req):
                        best_rate = rate
                        best_link = {"method": "relay", "ground_station": gs["id"], "relay": geo["id"], "relay2": None, "rate": rate}

        return best_link
