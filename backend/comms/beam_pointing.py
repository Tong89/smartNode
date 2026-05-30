# -*- coding: utf-8 -*-
"""波束指向与相控阵扫描约束建模（Beam Pointing & Phased-Array Scan Constraints）。

将配置中 OPPORTUNISTIC_STATIONS 与 GEO_RELAY_SATELLITES 的
phased_array/beams 参数转化为可执行的指向约束：

- **scan_range 校验**：检查目标方位角/仰角是否落入天线扫描范围；
  超出范围的指向直接拒绝（该波束不可用）。
- **偏轴扫描损耗**：cos 扫描损耗模型，将偏离天线法线的扫描角折算为增益损耗 (dB)，
  并映射到可达链路速率衰减系数。
- **max_beams 约束**：当前活跃波束数不得超过 max_beams；
  超限时拒绝新的指向请求。
- **scan_speed 重指向时间**：根据当前指向与目标夹角和扫描速率，
  计算重新指向所需时间（ms）；若超过容忍阈值则通知调用方需等待。

公开接口
--------
- :class:`BeamPointing`       — 面向对象接口，持有一个天线/波束管理器的状态。
- :func:`check_scan_range`    — 纯函数：方位/仰角是否在扫描范围内。
- :func:`scan_loss_db`        — 偏轴扫描损耗 (dB)，基于余弦模型。
- :func:`scan_loss_factor`    — 偏轴损耗对应的功率因子（线性，<=1.0）。
- :func:`rate_with_scan_loss` — 将扫描损耗折算到可达速率 (Mbps)。
- :func:`repoint_time_ms`     — 从当前指向切换到目标指向所需时间 (ms)。
"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════
#  纯函数
# ═══════════════════════════════════════════════════════════════

def check_scan_range(
    azimuth_deg: float,
    elevation_deg: float,
    scan_range: Dict[str, Tuple[float, float]],
) -> bool:
    """检查目标方位角/仰角是否落入扫描范围。

    Parameters
    ----------
    azimuth_deg : float
        目标方位角（度）。对于相控阵天线，通常以天线法线为零点，
        范围约 ±60°（即 ``scan_range["azimuth"]``）。
    elevation_deg : float
        目标仰角（度），相对于水平面，范围 0-90°。
    scan_range : dict
        扫描范围字典，含键 ``"azimuth"`` 与 ``"elevation"``，
        每项均为 ``(min_deg, max_deg)`` 元组，例如：
        ``{"azimuth": (-60, 60), "elevation": (10, 90)}``.

    Returns
    -------
    bool
        ``True`` 表示目标在扫描范围内，``False`` 表示超出范围（波束不可用）。
    """
    az_min, az_max = scan_range["azimuth"]
    el_min, el_max = scan_range["elevation"]

    if not (az_min <= azimuth_deg <= az_max):
        return False
    if not (el_min <= elevation_deg <= el_max):
        return False
    return True


def scan_loss_db(
    azimuth_deg: float,
    elevation_deg: float,
    az_center: float = 0.0,
    el_center: float = 90.0,
) -> float:
    """计算相控阵偏轴扫描损耗（dB）。

    采用余弦扫描损耗模型：
        L_scan(dB) = −20·log10(cos(θ_scan))
    其中 θ_scan 为目标方向与天线法线方向之间的夹角（0°=法线方向）。

    对于仰角系统（法线指向天顶）：
        cos(θ_scan) = cos(|az − az_center|) · sin(elevation_deg)
    其中 sin(elevation_deg) 项对仰角的偏离做修正。

    Parameters
    ----------
    azimuth_deg : float
        目标方位角（度）。
    elevation_deg : float
        目标仰角（度）。
    az_center : float
        天线法线方位角（度），默认 0（正北/正前方）。
    el_center : float
        天线法线仰角（度），默认 90°（天顶）。
        对于固定向上的平面阵，天线法线指天顶。

    Returns
    -------
    float
        扫描损耗（dB），非负值，值越大表示损耗越大。
        当目标与法线重合（θ_scan=0）时返回 0.0。
    """
    # 方位偏差（度）
    delta_az = azimuth_deg - az_center
    delta_el = elevation_deg - el_center

    # 将方位和仰角偏差转为三维夹角（近似球面投影）
    delta_az_rad = math.radians(delta_az)
    delta_el_rad = math.radians(delta_el)

    # 余弦叠加：cos(θ) ≈ cos(Δaz)·cos(Δel)（法线方向 = az_center, el_center）
    cos_theta = math.cos(delta_az_rad) * math.cos(delta_el_rad)
    # 夹紧到 [epsilon, 1.0]，避免 log(0)
    cos_theta = max(cos_theta, 1e-6)

    loss = -20.0 * math.log10(cos_theta)
    return max(loss, 0.0)


def scan_loss_factor(
    azimuth_deg: float,
    elevation_deg: float,
    az_center: float = 0.0,
    el_center: float = 90.0,
) -> float:
    """偏轴扫描损耗对应的功率因子（线性，<=1.0）。

    Returns
    -------
    float
        功率因子 0 < factor <= 1.0；
        factor=1.0 表示无损耗（正对法线），越小表示损耗越大。
    """
    loss_db = scan_loss_db(azimuth_deg, elevation_deg, az_center, el_center)
    return 10.0 ** (-loss_db / 10.0)


def rate_with_scan_loss(
    base_rate_mbps: float,
    azimuth_deg: float,
    elevation_deg: float,
    az_center: float = 0.0,
    el_center: float = 90.0,
) -> float:
    """将偏轴扫描损耗折算到可达速率。

    假设速率与信噪比线性相关（Shannon容量在线性域中与 SNR 单调），
    此处简化为：可达速率 ∝ 功率因子（线性近似）。

    Parameters
    ----------
    base_rate_mbps : float
        无扫描损耗时的基准可达速率 (Mbps)。
    azimuth_deg : float
        目标方位角（度）。
    elevation_deg : float
        目标仰角（度）。
    az_center : float
        天线法线方位角（度）。
    el_center : float
        天线法线仰角（度）。

    Returns
    -------
    float
        考虑扫描损耗后的可达速率 (Mbps)。
    """
    factor = scan_loss_factor(azimuth_deg, elevation_deg, az_center, el_center)
    return base_rate_mbps * factor


def repoint_time_ms(
    current_az_deg: float,
    current_el_deg: float,
    target_az_deg: float,
    target_el_deg: float,
    scan_speed_deg_per_ms: float,
) -> float:
    """计算从当前指向切换到目标指向所需时间 (ms)。

    以二范数计算角度空间中的欧氏距离作为扫描角变化量，
    除以 scan_speed 得到重指向时间。

    Parameters
    ----------
    current_az_deg : float
        当前指向方位角（度）。
    current_el_deg : float
        当前指向仰角（度）。
    target_az_deg : float
        目标方位角（度）。
    target_el_deg : float
        目标仰角（度）。
    scan_speed_deg_per_ms : float
        扫描速度（度/ms），取自 phased_array["scan_speed"]。

    Returns
    -------
    float
        重指向所需时间（ms），若当前指向与目标重合则返回 0.0。
    """
    if scan_speed_deg_per_ms <= 0:
        raise ValueError(f"scan_speed_deg_per_ms must be positive, got {scan_speed_deg_per_ms}")

    delta_az = target_az_deg - current_az_deg
    delta_el = target_el_deg - current_el_deg
    angular_distance = math.sqrt(delta_az ** 2 + delta_el ** 2)

    return angular_distance / scan_speed_deg_per_ms


# ════════════════════════════════════��══════════════════════════
#  数据类
# ═══════════════════════════════════════════════════════════════

@dataclass
class BeamPointingResult:
    """波束指向约束校验结果。"""

    # 目标指向（输入）
    azimuth_deg: float
    elevation_deg: float

    # 扫描范围校验
    in_scan_range: bool            # 是否在扫描范围内

    # 扫描损耗
    scan_loss_db: float            # 偏轴增益损耗 (dB)
    scan_loss_factor: float        # 功率线性因子 (0, 1]

    # 波束数约束
    active_beams: int              # 当前活跃波束数
    max_beams: int                 # 最大允许同时波束数
    beams_available: bool          # 是否还有可用波束槽位

    # 重指向时间
    repoint_time_ms: float         # 重指向所需时间 (ms)

    # 综合可用性
    is_available: bool             # 综合评判：波束是否可用
    unavailable_reason: Optional[str] = None  # 不可用原因

    def to_dict(self) -> dict:
        return {
            "azimuth_deg": round(self.azimuth_deg, 3),
            "elevation_deg": round(self.elevation_deg, 3),
            "in_scan_range": self.in_scan_range,
            "scan_loss_db": round(self.scan_loss_db, 3),
            "scan_loss_factor": round(self.scan_loss_factor, 6),
            "active_beams": self.active_beams,
            "max_beams": self.max_beams,
            "beams_available": self.beams_available,
            "repoint_time_ms": round(self.repoint_time_ms, 3),
            "is_available": self.is_available,
            "unavailable_reason": self.unavailable_reason,
        }


# ═══════════════════════════════════════════════════════════════
#  BeamPointing 类
# ═══════════════════════════════════════════════════════════════

class BeamPointing:
    """相控阵波束指向约束管理器。

    持有单个天线（站点）的波束状态，支持：
    - 检查新指向请求是否满足扫描范围约束；
    - 计算偏轴扫描损耗并折算到速率；
    - 跟踪当前活跃波束数，强制执行 max_beams 约束；
    - 计算重指向时间。

    Parameters
    ----------
    antenna_config : dict
        天线配置字典，支持两种来源：

        *OPPORTUNISTIC_STATIONS 格式*（phased_array / beam_management）::

            {
                "phased_array": {
                    "scan_range": {"azimuth": (-60, 60), "elevation": (10, 90)},
                    "scan_speed": 0.1,            # 度/ms
                    "pointing_accuracy": 0.05,
                },
                "beam_management": {
                    "max_beams": 16,
                    "beam_width": 2.0,
                }
            }

        *GEO_RELAY_SATELLITES 格式*（antenna / beams）::

            {
                "antenna": {
                    "scan_range": {"azimuth": (-60, 60), "elevation": (10, 90)},
                    "beam_count": 4,
                    "beam_gain": 50,
                },
                "beams": [
                    {"id": "B1", "azimuth": 0, "elevation": 45, "status": "free"},
                    ...
                ]
            }

    station_id : str, optional
        站点/卫星 ID（用于日志/调试），默认 "UNKNOWN"。
    """

    def __init__(self, antenna_config: dict, station_id: str = "UNKNOWN") -> None:
        self.station_id = station_id
        self._lock = threading.Lock()

        # ── 解析配置 ──────────────────────────────────────────
        if "phased_array" in antenna_config:
            # OPPORTUNISTIC_STATIONS 格式
            pa = antenna_config["phased_array"]
            bm = antenna_config.get("beam_management", {})
            self.scan_range: Dict[str, Tuple[float, float]] = pa["scan_range"]
            self.scan_speed: float = float(pa.get("scan_speed", 0.1))  # 度/ms
            self.pointing_accuracy: float = float(pa.get("pointing_accuracy", 0.05))
            self.max_beams: int = int(bm.get("max_beams", 16))
            self.beam_width: float = float(bm.get("beam_width", 2.0))
            self._beam_source = "phased_array"
        elif "antenna" in antenna_config:
            # GEO_RELAY_SATELLITES 格式
            ant = antenna_config["antenna"]
            self.scan_range = ant["scan_range"]
            # GEO 天线无 scan_speed 字段，使用典型值 0.05 度/ms（电子扫描快）
            self.scan_speed = float(ant.get("scan_speed", 0.05))
            self.pointing_accuracy = float(ant.get("pointing_accuracy", 0.02))
            self.max_beams = int(ant.get("beam_count", 4))
            self.beam_width = float(ant.get("beam_width", 0.5))
            self._beam_source = "geo_antenna"
        else:
            raise ValueError(
                f"antenna_config for station '{station_id}' must contain "
                "'phased_array' or 'antenna' key."
            )

        # ── 天线法线方向（默认指向天顶/正上方）────────────────
        self.az_center: float = 0.0
        self.el_center: float = 90.0  # 平面阵法线朝上

        # ── 活跃波束跟踪 ──────────────────────────────────────
        # {beam_key: {"azimuth": ..., "elevation": ..., "target_id": ...}}
        self._active_beams: Dict[str, dict] = {}

        # ── 当前指向（最近使用的指向，��于重指向计算） ─────────
        self._current_az: float = 0.0
        self._current_el: float = float(
            (self.scan_range["elevation"][0] + self.scan_range["elevation"][1]) / 2
        )

    # ── 公开属性 ────────────────────────────────────────────────

    @property
    def active_beam_count(self) -> int:
        """当前活跃波束数。"""
        with self._lock:
            return len(self._active_beams)

    @property
    def available_beam_slots(self) -> int:
        """剩余可用波束槽位数。"""
        with self._lock:
            return max(0, self.max_beams - len(self._active_beams))

    # ── 核心方法 ────────────────────────────────────────────────

    def check(
        self,
        azimuth_deg: float,
        elevation_deg: float,
        target_id: Optional[str] = None,
        repoint_tolerance_ms: float = 1000.0,
    ) -> BeamPointingResult:
        """校验对目标 (azimuth, elevation) 的波束指向请求。

        Parameters
        ----------
        azimuth_deg : float
            目标方位角（度），相对天线法线方向。
        elevation_deg : float
            目标仰角（度），相对水平面。
        target_id : str, optional
            目标标识（卫星 ID 或地面站 ID），用于去重检查。
        repoint_tolerance_ms : float
            允许的最大重指向时间（ms）；超过此值则认为当前无法立即使用，默认 1000 ms。

        Returns
        -------
        BeamPointingResult
        """
        with self._lock:
            # 1. 扫描范围检查
            in_range = check_scan_range(azimuth_deg, elevation_deg, self.scan_range)
            if not in_range:
                return BeamPointingResult(
                    azimuth_deg=azimuth_deg,
                    elevation_deg=elevation_deg,
                    in_scan_range=False,
                    scan_loss_db=float("inf"),
                    scan_loss_factor=0.0,
                    active_beams=len(self._active_beams),
                    max_beams=self.max_beams,
                    beams_available=self.available_beam_slots > 0,
                    repoint_time_ms=0.0,
                    is_available=False,
                    unavailable_reason="目标超出方位/仰角扫描范围",
                )

            # 2. 扫描损耗
            loss_db = scan_loss_db(
                azimuth_deg, elevation_deg,
                az_center=self.az_center, el_center=self.el_center
            )
            loss_factor = scan_loss_factor(
                azimuth_deg, elevation_deg,
                az_center=self.az_center, el_center=self.el_center
            )

            # 3. 最大波束数约束
            active_count = len(self._active_beams)
            beams_available = active_count < self.max_beams
            if not beams_available:
                return BeamPointingResult(
                    azimuth_deg=azimuth_deg,
                    elevation_deg=elevation_deg,
                    in_scan_range=True,
                    scan_loss_db=loss_db,
                    scan_loss_factor=loss_factor,
                    active_beams=active_count,
                    max_beams=self.max_beams,
                    beams_available=False,
                    repoint_time_ms=0.0,
                    is_available=False,
                    unavailable_reason=f"同时活动波束数已达上限 {self.max_beams}",
                )

            # 4. 重指向时间
            rp_time = repoint_time_ms(
                self._current_az, self._current_el,
                azimuth_deg, elevation_deg,
                self.scan_speed,
            )
            repoint_ok = rp_time <= repoint_tolerance_ms

            if not repoint_ok:
                return BeamPointingResult(
                    azimuth_deg=azimuth_deg,
                    elevation_deg=elevation_deg,
                    in_scan_range=True,
                    scan_loss_db=loss_db,
                    scan_loss_factor=loss_factor,
                    active_beams=active_count,
                    max_beams=self.max_beams,
                    beams_available=True,
                    repoint_time_ms=rp_time,
                    is_available=False,
                    unavailable_reason=(
                        f"重指向时间 {rp_time:.1f}ms 超过容忍阈值 {repoint_tolerance_ms:.1f}ms"
                    ),
                )

            return BeamPointingResult(
                azimuth_deg=azimuth_deg,
                elevation_deg=elevation_deg,
                in_scan_range=True,
                scan_loss_db=loss_db,
                scan_loss_factor=loss_factor,
                active_beams=active_count,
                max_beams=self.max_beams,
                beams_available=True,
                repoint_time_ms=rp_time,
                is_available=True,
            )

    def allocate(
        self,
        beam_key: str,
        azimuth_deg: float,
        elevation_deg: float,
        target_id: Optional[str] = None,
    ) -> bool:
        """分配��个活跃波束槽位，更新当前指向。

        Parameters
        ----------
        beam_key : str
            波束唯一标识（如请求 ID 或 ``"<station>-<target>"``）。
        azimuth_deg : float
            已经通过 :meth:`check` 验证的目标方位角（度）。
        elevation_deg : float
            目标仰角（度）。
        target_id : str, optional
            目标标识。

        Returns
        -------
        bool
            ``True`` 表示分配成功；``False`` 表示槽位已满或 key 已存在。
        """
        with self._lock:
            if beam_key in self._active_beams:
                return False
            if len(self._active_beams) >= self.max_beams:
                return False
            self._active_beams[beam_key] = {
                "azimuth": azimuth_deg,
                "elevation": elevation_deg,
                "target_id": target_id,
            }
            # 更新"当前指向"为最新分配方向，用于后续重指向时间计算
            self._current_az = azimuth_deg
            self._current_el = elevation_deg
            return True

    def release(self, beam_key: str) -> bool:
        """释放一个活跃波束槽位。

        Parameters
        ----------
        beam_key : str
            之前通过 :meth:`allocate` 分配的波束标识。

        Returns
        -------
        bool
            ``True`` 表示释放成功；``False`` 表示 key 不存在。
        """
        with self._lock:
            if beam_key in self._active_beams:
                del self._active_beams[beam_key]
                return True
            return False

    def apply_rate(self, base_rate_mbps: float, azimuth_deg: float, elevation_deg: float) -> float:
        """将扫描损耗折算到可达速率 (Mbps)。

        Parameters
        ----------
        base_rate_mbps : float
            无扫描损耗的基准可达速率 (Mbps)。
        azimuth_deg : float
            目标方位角（度）。
        elevation_deg : float
            目标仰角（度）。

        Returns
        -------
        float
            考虑偏轴扫描增益损耗后的可达速率 (Mbps)。
        """
        return rate_with_scan_loss(
            base_rate_mbps, azimuth_deg, elevation_deg,
            az_center=self.az_center, el_center=self.el_center,
        )

    def status(self) -> dict:
        """返回当前波束状态摘要。"""
        with self._lock:
            return {
                "station_id": self.station_id,
                "max_beams": self.max_beams,
                "active_beams": len(self._active_beams),
                "available_slots": max(0, self.max_beams - len(self._active_beams)),
                "current_pointing": {
                    "azimuth_deg": self._current_az,
                    "elevation_deg": self._current_el,
                },
                "scan_range": {
                    "azimuth": list(self.scan_range["azimuth"]),
                    "elevation": list(self.scan_range["elevation"]),
                },
                "scan_speed_deg_per_ms": self.scan_speed,
                "active_beam_list": [
                    {"key": k, **v} for k, v in self._active_beams.items()
                ],
            }


# ═══════════════════════════════════════════════════════════════
#  便捷工厂函数
# ═══════════════════════════════════════════════════════════════

def from_opportunistic_station(station: dict) -> BeamPointing:
    """从 OPPORTUNISTIC_STATIONS 配置条目创建 BeamPointing 实例。

    Parameters
    ----------
    station : dict
        ``OPPORTUNISTIC_STATIONS`` 列表中的一个条目，含 ``phased_array`` 与
        ``beam_management`` 子字典。

    Returns
    -------
    BeamPointing
    """
    return BeamPointing(
        antenna_config={
            "phased_array": station["phased_array"],
            "beam_management": station.get("beam_management", {}),
        },
        station_id=station.get("id", "OPP_UNKNOWN"),
    )


def from_geo_satellite(geo: dict) -> BeamPointing:
    """从 GEO_RELAY_SATELLITES 配置条目创建 BeamPointing 实例。

    Parameters
    ----------
    geo : dict
        ``GEO_RELAY_SATELLITES`` 列表中的一个条目，含 ``antenna`` 与
        ``beams`` 子字典。

    Returns
    -------
    BeamPointing
    """
    return BeamPointing(
        antenna_config={
            "antenna": geo["antenna"],
            "beams": geo.get("beams", []),
        },
        station_id=geo.get("id", "GEO_UNKNOWN"),
    )
