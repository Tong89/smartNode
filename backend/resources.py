# -*- coding: utf-8 -*-
"""资源占用与时间槽管理（ResourceManager）。

封装 resource_usage（即时占用）与 time_pool（时间维度预约）两套结构及其占用/释放/带宽与
时间槽校验逻辑，供引擎持有实例并统一调用，避免对内部嵌套 dict 的散落手动操作。
"""


class ResourceManager:
    def __init__(self):
        self.usage = {"satellites": {}, "ground_stations": {}, "geo_relays": {}}
        self.time_pool = {"satellites": {}, "ground_stations": {}, "geo_relays": {}}

    def init_pools(self, leo_sats, all_gs, geo_relays):
        self.time_pool = {
            "satellites": {s.sat_id: [] for s in leo_sats},
            "ground_stations": {gs["id"]: [] for gs in all_gs},
            "geo_relays": {geo["id"]: [] for geo in geo_relays},
        }

    def reset(self, leo_sats, all_gs, geo_relays):
        self.usage = {"satellites": {}, "ground_stations": {}, "geo_relays": {}}
        self.init_pools(leo_sats, all_gs, geo_relays)

    # ---- 即时占用 ----
    def occupy(self, req_id, sat_id, gs_id, relay_id=None, relay2_id=None, start_time=None, end_time=None):
        self.usage["satellites"].setdefault(sat_id, [])
        if req_id not in self.usage["satellites"][sat_id]:
            self.usage["satellites"][sat_id].append(req_id)
        if gs_id:
            self.usage["ground_stations"].setdefault(gs_id, [])
            if req_id not in self.usage["ground_stations"][gs_id]:
                self.usage["ground_stations"][gs_id].append(req_id)
        for rid in (relay_id, relay2_id):
            if rid:
                self.usage["geo_relays"].setdefault(rid, [])
                if req_id not in self.usage["geo_relays"][rid]:
                    self.usage["geo_relays"][rid].append(req_id)

        if start_time is not None and end_time is not None:
            self.reserve_time_slot("satellites", sat_id, start_time, end_time, req_id)
            if gs_id:
                self.reserve_time_slot("ground_stations", gs_id, start_time, end_time, req_id)
            for rid in (relay_id, relay2_id):
                if rid:
                    self.reserve_time_slot("geo_relays", rid, start_time, end_time, req_id)

    def occupy_satellite_only(self, req_id, sat_id):
        self.usage["satellites"].setdefault(sat_id, [])
        self.usage["satellites"][sat_id].append(req_id)

    def release(self, req_id):
        for resource_dict in self.usage.values():
            for resource_id, req_list in list(resource_dict.items()):
                if req_id in req_list:
                    req_list.remove(req_id)
                if len(req_list) == 0:
                    del resource_dict[resource_id]
        self.release_time_slot(req_id)

    # ---- 时间槽 ----
    def check_time_slot_available(self, resource_type, resource_id, start_time, end_time,
                                  required_bandwidth=0, geo_relays=None):
        if resource_type not in self.time_pool:
            return False, "无效的资源类型"
        if resource_id not in self.time_pool[resource_type]:
            return False, f"资源 {resource_id} 不存在"
        time_slots = self.time_pool[resource_type][resource_id]
        for slot in time_slots:
            slot_start, slot_end, req_id, slot_bw = slot
            if not (end_time <= slot_start or start_time >= slot_end):
                if resource_type == "geo_relays":
                    geo = next((g for g in (geo_relays or []) if g["id"] == resource_id), None)
                    if geo:
                        max_bw = geo.get("bandwidth", 2000)
                        used_bw = sum(s[3] for s in time_slots
                                      if not (end_time <= s[0] or start_time >= s[1]))
                        if used_bw + required_bandwidth > max_bw:
                            return False, f"中继 {resource_id} 带宽不足 (已用:{used_bw:.0f}, 需要:{required_bandwidth:.0f}, 上限:{max_bw})"
                else:
                    return False, f"资源 {resource_id} 在时间段 {slot_start:.0f}-{slot_end:.0f} 已被 {req_id} 占用"
        return True, "可用"

    def reserve_time_slot(self, resource_type, resource_id, start_time, end_time, req_id, bandwidth=0):
        if resource_type in self.time_pool and resource_id in self.time_pool[resource_type]:
            self.time_pool[resource_type][resource_id].append((start_time, end_time, req_id, bandwidth))

    def release_time_slot(self, req_id):
        for resource_type in self.time_pool:
            for resource_id in self.time_pool[resource_type]:
                self.time_pool[resource_type][resource_id] = [
                    slot for slot in self.time_pool[resource_type][resource_id] if slot[2] != req_id
                ]

    def cleanup_expired(self, current_time):
        for resource_type in self.time_pool:
            for resource_id in self.time_pool[resource_type]:
                self.time_pool[resource_type][resource_id] = [
                    slot for slot in self.time_pool[resource_type][resource_id] if slot[1] > current_time
                ]

    def get_schedule(self, resource_type, resource_id, current_time, time_range=3600):
        if resource_type not in self.time_pool or resource_id not in self.time_pool[resource_type]:
            return []
        end_time = current_time + time_range
        return [
            {"start": slot[0], "end": slot[1], "request_id": slot[2], "bandwidth": slot[3]}
            for slot in self.time_pool[resource_type][resource_id]
            if slot[1] > current_time and slot[0] < end_time
        ]
