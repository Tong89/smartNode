# -*- coding: utf-8 -*-
"""链路选路与重调度（Scheduler）。

集中承载链路可用性判定、最佳链路搜索与重调度逻辑。持有引擎引用以读取资源/星座快照与
几何/速率计算，引擎仅以薄方法委托，行为与重构前一致。
"""
from backend.orbit import calc_central_angle


class Scheduler:
    def __init__(self, engine, strategy=None):
        self.engine = engine
        if strategy is None:
            from backend.scheduling.strategy import GreedyMaxRateStrategy
            strategy = GreedyMaxRateStrategy()
        self.strategy = strategy

    def resource_busy_by_other(self, resource_type, resource_id, req_id):
        return any(
            existing_req_id != req_id
            for existing_req_id in self.engine.resource_usage.get(resource_type, {}).get(resource_id, [])
        )

    def ground_station_candidates(self, req):
        if req.selected_ground_stations:
            selected = set(req.selected_ground_stations)
            return [gs for gs in self.engine.ground_stations if gs["id"] in selected]
        return self.engine.ground_stations

    def relay_can_carry_request(self, relay_id, required_rate, req):
        if relay_id in [req.selected_relay, req.selected_relay2]:
            return True
        return self.engine._check_relay_bandwidth_available(relay_id, required_rate)

    def find_best_available_link(self, req, satellite, sat_pos):
        return self.strategy.select(self, req, satellite, sat_pos)

    def current_link_available(self, req, sat_pos):
        eng = self.engine
        if req.transmission_method == "direct":
            gs = next((item for item in eng.ground_stations if item["id"] == req.selected_ground_station), None)
            return bool(gs and eng.check_visibility(sat_pos, gs, min_elevation=5))

        if req.transmission_method == "relay":
            geo = next((item for item in eng.geo_relays if item["id"] == req.selected_relay), None)
            gs = next((item for item in eng.ground_stations if item["id"] == req.selected_ground_station), None)
            if not geo or not gs:
                return False
            geo_pos = eng.get_geo_position(geo)
            return eng.check_geo_visibility(sat_pos, geo_pos) and eng.check_visibility(geo_pos, gs, min_elevation=5)

        if req.transmission_method == "multi_relay":
            geo1 = next((item for item in eng.geo_relays if item["id"] == req.selected_relay), None)
            geo2 = next((item for item in eng.geo_relays if item["id"] == req.selected_relay2), None)
            gs = next((item for item in eng.ground_stations if item["id"] == req.selected_ground_station), None)
            if not geo1 or not geo2 or not gs:
                return False
            geo1_pos = eng.get_geo_position(geo1)
            geo2_pos = eng.get_geo_position(geo2)
            geo_gap = calc_central_angle(geo1_pos["lat"], geo1_pos["lon"], geo2_pos["lat"], geo2_pos["lon"])
            return (
                eng.check_geo_visibility(sat_pos, geo1_pos)
                and geo_gap < 140
                and eng.check_visibility(geo2_pos, gs, min_elevation=5)
            )
        return False

    def apply_link_assignment(self, req, satellite, link):
        eng = self.engine
        eng._release_resources(req.id)
        req.transmission_method = link["method"]
        req.selected_ground_station = link["ground_station"]
        req.selected_relay = link["relay"]
        req.selected_relay2 = link["relay2"]
        req.transmission_rate = link["rate"]
        eng._occupy_resources(req.id, satellite.sat_id, req.selected_ground_station, req.selected_relay, req.selected_relay2)

    def reroute_transmission(self, req, satellite, sat_pos):
        link = self.find_best_available_link(req, satellite, sat_pos)
        if not link:
            return False
        old_method = req.transmission_method
        self.apply_link_assignment(req, satellite, link)
        self.engine._log(
            f"链路重调度: {old_method} -> {req.transmission_method}, 速率:{req.transmission_rate:.1f}Mbps",
            request=req, level="normal",
        )
        return True
