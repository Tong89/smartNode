# -*- coding: utf-8 -*-
"""链路切换控制器：迟滞带 + 最小驻留时间 + 冷却期，统一约束所有链路切换，避免乒乓效应。"""


class HandoverController:
    def __init__(self, rate_ratio, min_dwell, cooldown, min_elevation):
        self.rate_ratio = rate_ratio        # 迟滞带：新链路收益须超过当前速率的倍数
        self.min_dwell = min_dwell          # 最小驻留时间（自开始传输起）
        self.cooldown = cooldown            # 两次切换之间的冷却期
        self.min_elevation = min_elevation  # 候选链路最小仰角（防低仰角抖动）
        self._last_switch = {}              # req_id -> 上次切换的仿真时间

    def should_handover(self, req, current_time, new_rate):
        """是否允许切换到 new_rate 的新链路。"""
        current_rate = req.transmission_rate or 0
        if new_rate <= current_rate * self.rate_ratio:
            return False
        if req.start_transmit_time is not None and (current_time - req.start_transmit_time) < self.min_dwell:
            return False
        last = self._last_switch.get(req.id)
        if last is not None and (current_time - last) < self.cooldown:
            return False
        return True

    def record_switch(self, req, current_time):
        self._last_switch[req.id] = current_time

    def forget(self, req_id):
        self._last_switch.pop(req_id, None)
