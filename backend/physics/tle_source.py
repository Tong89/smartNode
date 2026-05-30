# -*- coding: utf-8 -*-
"""Celestrak TLE 导入器与离线缓存。

提供从 Celestrak GP 接口按 group/catnr 拉取两行根数（TLE）的函数，
将结果落地到 ``data/tle_cache/<group>.tle`` 并附带时间戳元数据。
离线或拉取失败时自动回退到本地缓存文件，确保系统不因网络故障崩溃。

典型用法::

    from backend.physics.tle_source import fetch_group, get_cache_status

    # 拉取 Starlink 星座 TLE（失败时使用缓存）
    entries = fetch_group("starlink")
    for name, line1, line2, epoch in entries:
        print(name, epoch)

    # 查看缓存新鲜度
    status = get_cache_status()
    print(status)
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger("smartnode.physics.tle_source")

# ---------------------------------------------------------------------------
# 路径与常量
# ---------------------------------------------------------------------------

# 项目根目录（本文件位于 backend/physics/tle_source.py）
_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = _PACKAGE_ROOT / "data" / "tle_cache"

# Celestrak GP REST 接口（3le 格式含名称行）
_CELESTRAK_GP_GROUP_URL = (
    "https://celestrak.org/SOCRATES/query.php?FORMAT=TLE&GROUP={group}"
)
_CELESTRAK_GP_GROUP_URL_MAIN = (
    "https://celestrak.org/SOCRATES/query.php?FORMAT=TLE&GROUP={group}"
)
# 主要使用 celestrak.org/pub/TLE 格式（TLE 原始三行格式）
_CELESTRAK_TLE_URL = "https://celestrak.org/pub/TLE/{group}.txt"
# Celestrak GP API（支持按 CATNR 查询）
_CELESTRAK_GP_CATNR_URL = (
    "https://celestrak.org/SOCRATES/query.php?FORMAT=TLE&CATNR={catnr}"
)
_CELESTRAK_GP_API_URL = (
    "https://celestrak.org/SOCRATES/query.php?FORMAT=TLE&NAME={name}"
)

# 各接口超时（秒）
_FETCH_TIMEOUT = 15

# 缓存有效期（秒）—— 默认 24 小时
_CACHE_MAX_AGE_SECONDS = int(os.environ.get("SMARTNODE_TLE_CACHE_TTL", 86400))

# 已知星座分组到 Celestrak TLE 文件名映射
_GROUP_ALIASES: dict[str, str] = {
    "starlink": "starlink",
    "oneweb": "oneweb",
    "gps-ops": "gps-ops",
    "galileo": "galileo",
    "beidou": "beidou",
    "glonass": "glo-ops",
    "glo-ops": "glo-ops",
    "iridium": "iridium",
    "iridium-next": "iridium-NEXT",
    "iridium-NEXT": "iridium-NEXT",
    "orbcomm": "orbcomm",
    "planet": "planet",
    "spire": "spire",
    "iss": "stations",
    "stations": "stations",
    "active": "active",
    "leo": "active",
    "meo": "active",
    "gnss": "gnss",
}

# TLE 条目类型：(name, line1, line2, epoch_utc)
TleEntry = Tuple[str, str, str, str]


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------

def _ensure_cache_dir() -> None:
    """确保缓存目录存在。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _cache_path(group: str) -> Path:
    """返回指定分组的缓存文件路径（.tle）。"""
    safe = group.replace("/", "_").replace(" ", "_")
    return CACHE_DIR / f"{safe}.tle"


def _meta_path(group: str) -> Path:
    """返回指定分组的元数据文件路径（.meta.json）。"""
    safe = group.replace("/", "_").replace(" ", "_")
    return CACHE_DIR / f"{safe}.meta.json"


def _write_cache(group: str, raw_text: str) -> None:
    """将拉取的 TLE 原始文本写入缓存文件并更新元数据。"""
    _ensure_cache_dir()
    cache_file = _cache_path(group)
    meta_file = _meta_path(group)

    cache_file.write_text(raw_text, encoding="utf-8")

    entries = _parse_tle_text(raw_text)
    meta = {
        "group": group,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "fetched_at_unix": time.time(),
        "entry_count": len(entries),
        "source": "celestrak",
    }
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("TLE 缓存已更新: group=%s, entries=%d", group, len(entries))


def _read_cache(group: str) -> Optional[str]:
    """读取本地缓存文件，不存在则返回 None。"""
    cache_file = _cache_path(group)
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    return None


def _cache_is_fresh(group: str) -> bool:
    """检查缓存文件是否在 TTL 期限内。"""
    meta_file = _meta_path(group)
    if not meta_file.exists():
        return False
    try:
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        age = time.time() - float(meta.get("fetched_at_unix", 0))
        return age < _CACHE_MAX_AGE_SECONDS
    except Exception:
        return False


def _parse_tle_text(text: str) -> List[TleEntry]:
    """解析 3 行格式的 TLE 文本（名称行 + 第一行 + 第二行）。

    支持：
    - 标准 3LE（每组三行）
    - 2LE（无名称行，每组两行，名称设为 catnr）
    - 自动跳过空行与注释行（# 开头）

    返回 (name, line1, line2, epoch) 列表，epoch 从 TLE line1 解析。
    """
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    entries: List[TleEntry] = []
    i = 0
    while i < len(lines):
        # 检测是否为 TLE 行（以 '1 ' 或 '2 ' 开头的68-69字符行）
        if (
            i + 1 < len(lines)
            and lines[i].startswith("1 ")
            and lines[i + 1].startswith("2 ")
        ):
            # 2LE 格式（前面没有名称行）
            line1, line2 = lines[i], lines[i + 1]
            name = line1[2:7].strip()  # CATNR 作为名称
            epoch = _epoch_from_line1(line1)
            entries.append((name, line1, line2, epoch))
            i += 2
        elif (
            i + 2 < len(lines)
            and lines[i + 1].startswith("1 ")
            and lines[i + 2].startswith("2 ")
        ):
            # 3LE 格式（名称 + 两行根数）
            name = lines[i].strip()
            line1, line2 = lines[i + 1], lines[i + 2]
            epoch = _epoch_from_line1(line1)
            entries.append((name, line1, line2, epoch))
            i += 3
        else:
            i += 1
    return entries


def _epoch_from_line1(line1: str) -> str:
    """从 TLE 第一行提取历元时间字符串（ISO 格式 UTC）。

    TLE line1 格式：字段 3 = 年份(2位) + 年内天数(小数)，位于列 18-32。
    """
    try:
        epoch_field = line1[18:32].strip()
        year2 = int(epoch_field[:2])
        day_of_year = float(epoch_field[2:])
        full_year = 2000 + year2 if year2 < 57 else 1900 + year2
        # 将年积日转换为日期
        epoch_dt = datetime(full_year, 1, 1, tzinfo=timezone.utc) + __import__("datetime").timedelta(days=day_of_year - 1)
        return epoch_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# 公开 API：拉取函数
# ---------------------------------------------------------------------------

def fetch_group(
    group: str,
    force_refresh: bool = False,
) -> List[TleEntry]:
    """按星座分组名称拉取 TLE 条目。

    首先尝试从 Celestrak 在线拉取；若拉取失败或超时，则回退到本地缓存。
    若既无网络也无缓存，返回空列表并记录警告。

    参数
    ----
    group : str
        星座/分组标识，例如 ``"starlink"``、``"gps-ops"``、``"stations"``。
        支持别名映射（见 ``_GROUP_ALIASES``）。
    force_refresh : bool
        为 True 时即使缓存未过期也强制拉取，默认 False。

    返回
    ----
    list of TleEntry
        每条记录为 (name, line1, line2, epoch_utc) 元组。
    """
    canonical = _GROUP_ALIASES.get(group, group)

    # 检查缓存新鲜度
    if not force_refresh and _cache_is_fresh(canonical):
        logger.debug("使用新鲜 TLE 缓存: group=%s", canonical)
        cached = _read_cache(canonical)
        if cached:
            return _parse_tle_text(cached)

    # 尝试在线拉取
    url = _CELESTRAK_TLE_URL.format(group=canonical)
    try:
        raw_text = _http_get(url, timeout=_FETCH_TIMEOUT)
        if raw_text and len(raw_text.strip()) > 0:
            _write_cache(canonical, raw_text)
            return _parse_tle_text(raw_text)
        else:
            logger.warning("Celestrak 返回空响应: group=%s url=%s", canonical, url)
    except urllib.error.URLError as exc:
        logger.warning("Celestrak 拉取失败 (URLError): group=%s, error=%s", canonical, exc)
    except Exception as exc:  # pragma: no cover
        logger.warning("Celestrak 拉取异常: group=%s, error=%s", canonical, exc)

    # 回退到缓存
    cached = _read_cache(canonical)
    if cached:
        logger.info("网络不可用，使用离线 TLE 缓存: group=%s", canonical)
        return _parse_tle_text(cached)

    logger.warning("无法获取 TLE：在线拉取失败且无本地缓存: group=%s", canonical)
    return []


def fetch_by_catnr(catnr: int, force_refresh: bool = False) -> List[TleEntry]:
    """按 NORAD 卫星编号（CATNR）拉取 TLE 条目。

    参数
    ----
    catnr : int
        NORAD 卫星目录编号（如 25544 为 ISS）。
    force_refresh : bool
        强制刷新，忽略缓存。

    返回
    ----
    list of TleEntry
        通常包含 0 或 1 条记录。
    """
    group_key = f"catnr_{catnr}"

    if not force_refresh and _cache_is_fresh(group_key):
        cached = _read_cache(group_key)
        if cached:
            return _parse_tle_text(cached)

    url = f"https://celestrak.org/SOCRATES/query.php?FORMAT=TLE&CATNR={catnr}"
    try:
        raw_text = _http_get(url, timeout=_FETCH_TIMEOUT)
        if raw_text and raw_text.strip():
            _write_cache(group_key, raw_text)
            return _parse_tle_text(raw_text)
    except Exception as exc:
        logger.warning("Celestrak CATNR 拉取失败: catnr=%d, error=%s", catnr, exc)

    cached = _read_cache(group_key)
    if cached:
        return _parse_tle_text(cached)
    return []


def _http_get(url: str, timeout: int = 15) -> str:
    """执行 HTTP GET 请求，返回响应文本。"""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "SmartNode-TLE-Importer/1.0 (satellite simulation)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# 缓存状态查询
# ---------------------------------------------------------------------------

def get_cache_status() -> dict:
    """返回本地 TLE 缓存目录的状态摘要。

    返回
    ----
    dict
        包含以下字段：

        - ``cache_dir`` (str): 缓存目录绝对路径
        - ``entries`` (list): 每个缓存文件的摘要列表
        - ``total_groups`` (int): 缓存的星座/分组总数
        - ``total_tles`` (int): 缓存的 TLE 条目总数
    """
    _ensure_cache_dir()
    entries = []
    total_tles = 0

    for meta_file in sorted(CACHE_DIR.glob("*.meta.json")):
        try:
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            group = meta.get("group", meta_file.stem.replace(".meta", ""))
            fetched_at = meta.get("fetched_at", "")
            entry_count = int(meta.get("entry_count", 0))
            fetched_at_unix = float(meta.get("fetched_at_unix", 0))
            age_seconds = int(time.time() - fetched_at_unix)
            is_fresh = age_seconds < _CACHE_MAX_AGE_SECONDS

            cache_file = _cache_path(group)
            file_size = cache_file.stat().st_size if cache_file.exists() else 0

            entries.append({
                "group": group,
                "fetched_at": fetched_at,
                "age_seconds": age_seconds,
                "is_fresh": is_fresh,
                "entry_count": entry_count,
                "file_size_bytes": file_size,
                "cache_file": str(cache_file),
            })
            total_tles += entry_count
        except Exception as exc:
            logger.debug("读取缓存元数据失败: %s, error=%s", meta_file, exc)

    return {
        "cache_dir": str(CACHE_DIR),
        "entries": entries,
        "total_groups": len(entries),
        "total_tles": total_tles,
        "cache_ttl_seconds": _CACHE_MAX_AGE_SECONDS,
    }


def inject_tle_into_constellation(
    entries: List[TleEntry],
    satellites: list,
    max_inject: int = 0,
) -> int:
    """将拉取的 TLE 条目注入到星座卫星配置列表。

    遍历 ``satellites`` 列表，按卫星名称模糊匹配 TLE 条目并设置
    ``tle_line1`` / ``tle_line2`` 属性（若对象支持）。

    参数
    ----
    entries : list of TleEntry
        由 :func:`fetch_group` 返回的 TLE 条目列表。
    satellites : list
        星座卫星对象列表（需具有 ``name`` 属性和可写的 ``tle_line1`` / ``tle_line2``）。
    max_inject : int
        最多注入的条目数（0 表示不限）。

    返回
    ----
    int
        成功注入 TLE 的卫星数量。
    """
    if not entries:
        return 0

    # 构建名称 -> TLE 映射（去重取最新历元）
    tle_map: dict[str, TleEntry] = {}
    for entry in entries:
        name, *_ = entry
        tle_map[name.upper()] = entry

    injected = 0
    for sat in satellites:
        if max_inject > 0 and injected >= max_inject:
            break
        sat_name = getattr(sat, "name", "").upper()
        # 精确匹配
        matched = tle_map.get(sat_name)
        if matched is None:
            # 模糊匹配：包含关系
            for tle_name, entry in tle_map.items():
                if sat_name in tle_name or tle_name in sat_name:
                    matched = entry
                    break
        if matched:
            _, line1, line2, epoch = matched
            try:
                sat.tle_line1 = line1
                sat.tle_line2 = line2
                logger.debug(
                    "TLE 注入: sat=%s, epoch=%s", sat_name, epoch
                )
                injected += 1
            except Exception as exc:
                logger.warning("TLE 注入失败: sat=%s, error=%s", sat_name, exc)

    logger.info("TLE 注入完成: injected=%d/%d", injected, len(satellites))
    return injected


# ---------------------------------------------------------------------------
# 支持的分组列表（供 API 端点使用）
# ---------------------------------------------------------------------------

SUPPORTED_GROUPS: List[str] = sorted(_GROUP_ALIASES.keys())
