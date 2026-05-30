# -*- coding: utf-8 -*-
"""Flask API and static frontend routes for SmartNode."""

import logging
import os
from pathlib import Path

from backend.__about__ import __version__
from backend.logging_config import get_logger

from flask import Flask, Response, jsonify, request, send_from_directory, stream_with_context

from flask import g

from backend.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    decode_token,
    init_auth,
)
from backend.config import GS_MAX_BANDWIDTH, SATELLITE_MAX_BANDWIDTH, debug_api_enabled, validate_config, get_bind_host, get_bind_port
from backend.envelope import ok
from backend.openapi import OPENAPI_SPEC, SWAGGER_HTML
from backend.errors import error_response, register_error_handlers
from backend.rbac import require_role
from backend.ratelimit import rate_limit
from backend.schemas import (
    ValidationError,
    validate_count_update,
    validate_request_submission,
)
import jwt as _jwt

from backend.core import (
    DATA_COMBINATIONS,
    DATA_QOS_LEVELS,
    DATA_SECURITY_LEVELS,
    DATA_TYPES,
    DATA_URGENCY_LEVELS,
    MAX_GROUND_STATION_COUNT,
    MIN_GROUND_STATION_COUNT,
    MIN_LEO_SATELLITE_COUNT,
    OPPORTUNISTIC_STATIONS,
    TIME_SCALE,
    TOTAL_DATA_COMBINATIONS,
    create_engine,
)

# 经工厂创建引擎并启动（导入 backend.core 本身不再起线程）
simulation_engine = create_engine(autostart=True)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / 'frontend'

logger = get_logger("smartnode.api")

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
# 限制请求体大小，防止超大 payload 耗尽资源
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1 MB

# 注册统一脱敏错误处理器（4xx/5xx 返回稳定错误码，不回传 traceback）
register_error_handlers(app)

# 注册可插拔 API Key 鉴权（未配置 SMARTNODE_API_KEY 时降级为开放模式）
init_auth(app)

# 注册 Prometheus /metrics 端点与 OTel 链路追踪（prometheus_client 缺失时降级）
from backend.metrics import init_metrics  # noqa: E402
init_metrics(app, simulation_engine)

# 启动 SSE 态势快照推送线程（每 2 秒向所有 SSE 订阅者推送全量快照）
from backend.stream import start_snapshot_thread  # noqa: E402
start_snapshot_thread(lambda: simulation_engine)


# CORS 来源白名单（逗号分隔，环境变量配置）；默认仅本机回环
ALLOWED_ORIGINS = {
    o.strip()
    for o in os.environ.get(
        "SMARTNODE_CORS_ORIGINS",
        "http://localhost:5000,http://127.0.0.1:5000",
    ).split(",")
    if o.strip()
}


@app.after_request
def add_api_headers(response):
    # 仅对白名单 Origin 回显放行，替代通配 '*'
    origin = request.headers.get('Origin')
    if origin and origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Vary'] = 'Origin'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-API-Key'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Cache-Control'] = 'no-store'

    # 安全响应头：缓解点击劫持、MIME 嗅探、Referrer 泄露等
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    # CSP：兼容现有前端（Cesium/Vue/lucide 走 unpkg CDN 与 worker/wasm/blob）
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://unpkg.com blob:; "
        "style-src 'self' 'unsafe-inline' https://unpkg.com; "
        "img-src 'self' data: blob: https:; "
        "worker-src 'self' blob:; "
        "connect-src 'self' https://unpkg.com; "
        "font-src 'self' data: https://unpkg.com; "
        "frame-ancestors 'none'; "
        "base-uri 'self'"
    )
    # 不泄露服务器版本细节
    response.headers['Server'] = 'smartnode'
    return response


# ==========================================
# 6. Flask API接口
# ==========================================
@app.route('/api/data')
def get_simulation_data():
    """获取仿真数据"""
    return jsonify(simulation_engine.get_system_data())


@app.route('/api/debug_status')
def get_debug_status():
    """获取调试状态 - 仅在显式开启 SMARTNODE_DEBUG_API 时可用，默认返回 404。"""
    if not debug_api_enabled():
        return error_response("NOT_FOUND")
    # 仅返回脱敏运行摘要，不暴露线程对象等实现细节
    thread_alive = bool(
        simulation_engine.simulation_thread and simulation_engine.simulation_thread.is_alive()
    )
    return ok({
        "simulation_running": simulation_engine.running,
        "simulation_thread_alive": thread_alive,
        "current_time": round(simulation_engine.current_time, 2),
        "active_requests": len(simulation_engine.transmission_requests),
        "history_count": len(simulation_engine.request_history),
    })


@app.route('/api/request', methods=['POST'])
@require_role('operator')
@rate_limit(30, 60)
def submit_transmission_request():
    """提交传输请求"""
    # 检查权限 - 仅管理员可提交请求
    
    data = request.get_json(silent=True)
    if data is None:
        return error_response("UNSUPPORTED_MEDIA_TYPE", "请求体必须为 application/json")
    try:
        validate_request_submission(data, allowed_data_types=set(DATA_TYPES.keys()))
    except ValidationError as ve:
        return error_response("VALIDATION_ERROR", details=ve.errors)

    try:
        result = simulation_engine.submit_request(data)
        # 业务级错误（如指定卫星不存在）返回 4xx，便于前端区分客户端错误与服务端异常
        if isinstance(result, dict) and result.get("status") == "error":
            return jsonify(result), 400
        return jsonify(result)
    except Exception:
        # 真实异常仅记录到服务端日志，响应体脱敏（不回传 traceback/路径/栈信息）
        logger.exception("提交请求失败")
        return error_response("INTERNAL_ERROR")


@app.route('/api/requests')
def get_all_transmission_requests():
    """获取所有用户传输请求（不包括背景任务）"""
    return jsonify(simulation_engine.get_all_requests())


# ──────────────────────────────────────────────────────────────
# /api/v1/requests  — 分页 + 过滤 + 排序（v1 专用，不走别名注册）
# ──────────────────────────────────────────────────────────────
VALID_STATUSES = {"pending", "accepted", "transmitting", "completed", "rejected"}
VALID_SORT_PARAMS = {
    "id", "-id",
    "submit_time", "-submit_time",
    "priority", "-priority",
    "status", "-status",
}


def _parse_positive_int(raw, name: str, default: int, maximum: int = 200):
    """将查询参数解析为正整数，非法时返回校验错误响应（None 表示解析成功）。"""
    if raw is None:
        return default, None
    try:
        value = int(raw)
    except (ValueError, TypeError):
        return None, ({"field": name, "message": "须为整数"}, 400)
    if value < 1:
        return None, ({"field": name, "message": "须为正整数（≥1）"}, 400)
    if value > maximum:
        return None, ({"field": name, "message": f"不得超过 {maximum}"}, 400)
    return value, None


@app.route('/api/v1/requests', methods=['GET'])
def get_requests_paginated():
    """分页、过滤与排序的请求列表接口。

    Query Parameters:
        page         (int, ≥1, default=1)
        page_size    (int, 1-200, default=20)
        status       (pending|accepted|transmitting|completed|rejected)
        data_type    (str)
        satellite_id (str)
        source       (user|background)
        sort         (id|-id|submit_time|-submit_time|priority|-priority|status|-status)
                     默认 -id（最新优先）
    """
    # ── 解析并校验 page / page_size ──────────────────────────
    page, err = _parse_positive_int(request.args.get("page"), "page", 1)
    if err is not None:
        field_err, _ = err
        return error_response("VALIDATION_ERROR", message=field_err["message"],
                              details=[field_err])

    page_size, err = _parse_positive_int(
        request.args.get("page_size"), "page_size", 20, maximum=200
    )
    if err is not None:
        field_err, _ = err
        return error_response("VALIDATION_ERROR", message=field_err["message"],
                              details=[field_err])

    # ── 枚举校验 ─────────────────────────────────────────────
    status_filter = request.args.get("status")
    if status_filter is not None and status_filter not in VALID_STATUSES:
        return error_response(
            "VALIDATION_ERROR",
            message=f"status 取值不合法，支持：{', '.join(sorted(VALID_STATUSES))}",
            details=[{"field": "status", "message": "取值不在允许列表内"}],
        )

    sort_param = request.args.get("sort", "-id")
    if sort_param not in VALID_SORT_PARAMS:
        return error_response(
            "VALIDATION_ERROR",
            message=f"sort 取值不合法，支持：{', '.join(sorted(VALID_SORT_PARAMS))}",
            details=[{"field": "sort", "message": "取值不在允许列表内"}],
        )

    data_type_filter = request.args.get("data_type") or None
    satellite_id_filter = request.args.get("satellite_id") or None
    source_filter = request.args.get("source") or None

    result = simulation_engine.get_requests_paginated(
        page=page,
        page_size=page_size,
        status=status_filter,
        data_type=data_type_filter,
        satellite_id=satellite_id_filter,
        source=source_filter,
        sort=sort_param,
    )

    return ok(result["items"], meta=result["meta"])


@app.route('/api/all_requests_with_background')
def get_all_requests_with_background():
    """获取所有请求（包括背景任务）- 用于资源时间线可视化"""
    with simulation_engine.lock:
        all_reqs = simulation_engine.transmission_requests + simulation_engine.request_history
        return jsonify([req.to_dict() for req in all_reqs])


@app.route('/api/system_info')
def get_system_info():
    """获取系统信息"""
    return ok({
        "time_scale": TIME_SCALE,
        "ground_station_count": len(simulation_engine.ground_stations),
        "total_ground_stations": len(simulation_engine.all_ground_stations),
        "min_ground_stations": MIN_GROUND_STATION_COUNT,
        "max_ground_stations": MAX_GROUND_STATION_COUNT,
        # ⭐ LEO卫星配置信息
        "leo_satellite_count": len(simulation_engine.leo_satellites),
        "total_leo_satellites": len(simulation_engine.all_leo_satellites),
        "min_leo_satellites": MIN_LEO_SATELLITE_COUNT,
        "max_leo_satellites": 99999,  # ⭐ 设置一个极大的数或前端处理为无限制
        "leo_count": len(simulation_engine.leo_satellites),
        "meo_count": len(simulation_engine.meo_satellites),
        "geo_count": len(simulation_engine.geo_relays),
        "data_types": DATA_TYPES
    })


@app.route('/api/resource_utilization')
def get_resource_utilization():
    """获取实时资源利用率数据"""
    stats = simulation_engine.get_stats()
    return jsonify({
        "resource_utilization": stats.get("resource_utilization", {}),
        "user_requests": stats.get("user_requests", 0),
        "background_requests": stats.get("background_requests", 0),
        "rejected_by_resource": stats.get("rejected_by_resource", 0),
        "total_requests": stats.get("total_requests", 0),
        "accepted_requests": stats.get("accepted_requests", 0),
        "rejected_requests": stats.get("rejected_requests", 0),
        # ⭐ 新增决策指标
        "decision_metrics": stats.get("decision_metrics", {}),
        "rejection_distribution": stats.get("rejection_distribution", {})
    })


@app.route('/api/resource_timeline')
def get_resource_timeline():
    """
    获取资源时间轴数据（用于资源占用可视化）
    返回所有资源（卫星、地面站、中继星）的时间占用情况
    """
    with simulation_engine.lock:
        current_time = simulation_engine.current_time
        time_window = 3600  # 显示过去1小时的时间窗口
        start_time = max(0, current_time - time_window)
        
        timeline_data = {
            "current_time": current_time,
            "time_range": [start_time, current_time],
            "satellites": {},
            "ground_stations": {},
            "geo_relays": {}
        }
        
        # 获取所有请求（包括历史）
        all_requests = simulation_engine.transmission_requests + simulation_engine.request_history
        
        # 初始化资源时间轴
        for sat in simulation_engine.leo_satellites:
            timeline_data["satellites"][sat.sat_id] = {
                "name": sat.name,
                "type": "LEO",
                "events": []
            }
        
        for gs in simulation_engine.ground_stations:
            gs_id = gs["id"]
            timeline_data["ground_stations"][gs_id] = {
                "name": gs["name"],
                "type": "GS",
                "antenna": gs["antenna_type"],
                "events": []
            }
        
        for geo in simulation_engine.geo_relays:
            geo_id = geo["id"]
            timeline_data["geo_relays"][geo_id] = {
                "name": geo["name"],
                "type": "GEO",
                "events": []
            }
        
        # 填充时间事件
        for req in all_requests:
            if req.status in ["transmitting", "completed"]:
                # 计算事件时间范围
                event_start = req.start_transmit_time if hasattr(req, 'start_transmit_time') else req.submit_time
                
                if req.status == "transmitting":
                    event_end = current_time
                elif req.status == "completed":
                    event_end = req.complete_time if hasattr(req, 'complete_time') else event_start + 100
                else:
                    continue
                
                # 只显示时间窗口内的事件
                if event_end < start_time or event_start > current_time:
                    continue
                
                event_start = max(event_start, start_time)
                event_end = min(event_end, current_time)
                
                # 创建事件对象
                event = {
                    "request_id": req.id,
                    "start": event_start,
                    "end": event_end,
                    "status": req.status,
                    "data_type": req.data_type,
                    "data_size": req.data_size,
                    "priority": req.priority,
                    "source": req.source,
                    "progress": req.progress if hasattr(req, 'progress') else 1.0
                }
                
                # 添加到卫星时间轴
                if req.satellite_id in timeline_data["satellites"]:
                    timeline_data["satellites"][req.satellite_id]["events"].append(event.copy())
                
                # 添加到地面站时间轴
                if hasattr(req, 'selected_ground_station') and req.selected_ground_station:
                    if req.selected_ground_station in timeline_data["ground_stations"]:
                        timeline_data["ground_stations"][req.selected_ground_station]["events"].append(event.copy())
                
                # 添加到中继星时间轴
                if hasattr(req, 'selected_relay') and req.selected_relay:
                    if req.selected_relay in timeline_data["geo_relays"]:
                        timeline_data["geo_relays"][req.selected_relay]["events"].append(event.copy())
                
                if hasattr(req, 'selected_relay2') and req.selected_relay2:
                    if req.selected_relay2 in timeline_data["geo_relays"]:
                        timeline_data["geo_relays"][req.selected_relay2]["events"].append(event.copy())
        
        return jsonify(timeline_data)


@app.route('/api/resource_status')
def get_resource_status():
    """
    ⭐ 资源状态API：展示各类资源的实时可用性
    包括卫星、地面站、中继星的占用/空闲状态
    """
    with simulation_engine.lock:
        current_time = simulation_engine.current_time
        
        result = {
            "current_time": current_time,
            "satellites": [],      # 卫星状态列表
            "ground_stations": [], # 地面站状态列表
            "geo_relays": [],      # 中继星状态列表
            "summary": {}
        }
        
        # =========================================
        # 1. 卫星资源状态（天基资源）
        # =========================================
        total_sats = len(simulation_engine.leo_satellites)
        busy_sats = 0
        total_sat_tasks = 0
        total_sat_bandwidth_used = 0.0
        
        # ⭐ 单星最大带宽设为600Mbps（考虑直连和中继叠加）
        # 单星最大带宽见 backend/config.py
        
        for sat in simulation_engine.leo_satellites:
            sat_id = sat.sat_id
            # 统计该卫星上的活跃任务
            active_tasks = [r for r in simulation_engine.transmission_requests 
                          if r.satellite_id == sat_id and r.status in ["accepted", "transmitting"]]
            task_count = len(active_tasks)
            total_sat_tasks += task_count
            
            # 计算该卫星当前使用的带宽
            bandwidth_used = sum(r.transmission_rate for r in active_tasks if r.status == "transmitting")
            total_sat_bandwidth_used += bandwidth_used
            
            # 判断状态
            is_busy = task_count > 0
            if is_busy:
                busy_sats += 1
            
            # 计算数据吞吐量
            data_in_progress = sum(r.data_size * (1 - r.progress/100) for r in active_tasks if r.status == "transmitting")
            
            # ⭐ 确保利用率不超过100%
            utilization = min(100.0, bandwidth_used / SATELLITE_MAX_BANDWIDTH * 100) if bandwidth_used > 0 else 0
            
            result["satellites"].append({
                "id": sat_id,
                "name": sat.name,
                "status": "busy" if is_busy else "idle",
                "task_count": task_count,
                "bandwidth_used": round(bandwidth_used, 1),
                "max_bandwidth": SATELLITE_MAX_BANDWIDTH,
                "utilization": round(utilization, 1),
                "data_pending": round(data_in_progress, 2)
            })
        
        # =========================================
        # 2. 地面站资源状态
        # =========================================
        total_gs = len(simulation_engine.ground_stations)
        busy_gs = 0
        
        # ⭐ 地面站最大带宽设为1000Mbps
        # 地面站最大带宽见 backend/config.py
        
        for gs in simulation_engine.ground_stations:
            gs_id = gs["id"]
            # 统计使用该地面站的任务
            active_tasks = [r for r in simulation_engine.transmission_requests 
                          if r.selected_ground_station == gs_id and r.status == "transmitting"]
            task_count = len(active_tasks)
            
            is_busy = task_count > 0
            if is_busy:
                busy_gs += 1
            
            # 计算接收带宽
            bandwidth_used = sum(r.transmission_rate for r in active_tasks)
            
            # ⭐ 确保利用率不超过100%
            utilization = min(100.0, bandwidth_used / GS_MAX_BANDWIDTH * 100) if bandwidth_used > 0 else 0
            
            result["ground_stations"].append({
                "id": gs_id,
                "name": gs["name"],
                "status": "busy" if is_busy else "idle",
                "task_count": task_count,
                "bandwidth_used": round(bandwidth_used, 1),
                "max_bandwidth": GS_MAX_BANDWIDTH,
                "utilization": round(utilization, 1),
                "antenna_type": gs.get("antenna_type", "unknown")
            })
        
        # =========================================
        # 3. 中继星资源状态
        # =========================================
        total_geo = len(simulation_engine.geo_relays)
        busy_geo = 0
        
        for geo in simulation_engine.geo_relays:
            geo_id = geo["id"]
            max_bw = geo.get("bandwidth", 2000)
            
            # 统计使用该中继的任务
            active_tasks = [r for r in simulation_engine.transmission_requests 
                          if (r.selected_relay == geo_id or r.selected_relay2 == geo_id) 
                          and r.status == "transmitting"]
            task_count = len(active_tasks)
            
            # 计算带宽占用
            bandwidth_used = sum(r.transmission_rate for r in active_tasks)
            
            is_busy = bandwidth_used > 0
            if is_busy:
                busy_geo += 1
            
            # ⭐ 确保利用率不超过100%，可用带宽不低于0
            utilization = min(100.0, bandwidth_used / max_bw * 100) if max_bw > 0 else 0
            bandwidth_available = max(0, max_bw - bandwidth_used)
            
            result["geo_relays"].append({
                "id": geo_id,
                "name": geo["name"],
                "lon": geo.get("lon", 0),  # ⭐ 添加经度信息
                "status": "busy" if is_busy else "idle",
                "task_count": task_count,
                "bandwidth_used": round(bandwidth_used, 1),
                "max_bandwidth": max_bw,
                "bandwidth_available": round(bandwidth_available, 1),
                "utilization": round(utilization, 1)
            })
        
        # =========================================
        # 4. 汇总统计
        # =========================================
        # 整体利用率：仅对非空资源类别按权重加权并重新归一，
        # 避免任一类别数量为 0 时整体利用率被错误置 0。
        _util_terms = []
        if total_sats > 0:
            _util_terms.append((0.5, busy_sats / total_sats))
        if total_gs > 0:
            _util_terms.append((0.3, busy_gs / total_gs))
        if total_geo > 0:
            _util_terms.append((0.2, busy_geo / total_geo))
        _weight_sum = sum(w for w, _ in _util_terms)
        overall_utilization = (
            sum(w * u for w, u in _util_terms) / _weight_sum if _weight_sum > 0 else 0
        )

        result["summary"] = {
            # 卫星（天基）
            "satellites_total": total_sats,
            "satellites_busy": busy_sats,
            "satellites_idle": total_sats - busy_sats,
            "satellites_utilization": round(busy_sats / total_sats * 100, 1) if total_sats > 0 else 0,
            "satellites_task_count": total_sat_tasks,
            "satellites_bandwidth_total": round(total_sat_bandwidth_used, 1),
            
            # 地面站
            "ground_stations_total": total_gs,
            "ground_stations_busy": busy_gs,
            "ground_stations_idle": total_gs - busy_gs,
            "ground_stations_utilization": round(busy_gs / total_gs * 100, 1) if total_gs > 0 else 0,
            
            # 中继星
            "geo_relays_total": total_geo,
            "geo_relays_busy": busy_geo,
            "geo_relays_idle": total_geo - busy_geo,
            "geo_relays_utilization": round(busy_geo / total_geo * 100, 1) if total_geo > 0 else 0,
            
            # 整体利用率（按非空类别动态归一的加权平均）
            "overall_utilization": round(overall_utilization * 100, 1)
        }
        
        return jsonify(result)


@app.route('/api/v1/stream')
def sse_stream_endpoint():
    """
    SSE 实时推送端点（GET /api/v1/stream）。

    以 ``text/event-stream`` 格式持续推送两类 SSE 事件：
    * ``snapshot`` – 每 2 秒推送一次完整态势快照（卫星位置、资源、请求列表）
    * ``event``    – 实时推送请求接受/拒绝/完成等调度事件

    客户端示例::

        const es = new EventSource('/api/v1/stream');
        es.addEventListener('snapshot', e => { const snap = JSON.parse(e.data); … });
        es.addEventListener('event',    e => { const evt  = JSON.parse(e.data); … });
    """
    from backend.stream import sse_stream  # local import to avoid circular at module level

    def generate():
        yield from sse_stream()

    resp = Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
    )
    resp.headers['Cache-Control'] = 'no-cache'
    resp.headers['X-Accel-Buffering'] = 'no'  # disable nginx proxy buffering
    return resp


@app.route('/api/update_ground_stations', methods=['POST'])
@require_role('admin')
@rate_limit(10, 60)
def update_ground_stations():
    """更新地面站数量"""
    # 检查权限 - 仅管理员可修改配置
    
    data = request.get_json(silent=True)
    if data is None:
        return error_response("UNSUPPORTED_MEDIA_TYPE", "请求体必须为 application/json")
    try:
        validate_count_update(data, lo=MIN_GROUND_STATION_COUNT, hi=MAX_GROUND_STATION_COUNT)
    except ValidationError as ve:
        return error_response("VALIDATION_ERROR", details=ve.errors)
    new_count = data['count']
    try:
        success = simulation_engine.update_ground_station_count(new_count)
        
        if success:
            return jsonify({
                "success": True,
                "message": f"地面站数量已更新为{new_count}个",
                "ground_station_count": len(simulation_engine.ground_stations)
            })
        else:
            return jsonify({
                "success": False,
                "message": "地面站数量未改变"
            })
    except Exception:
        logger.exception("接口处理失败")
        return error_response("INTERNAL_ERROR")

@app.route('/api/update_leo_satellites', methods=['POST'])
@require_role('admin')
@rate_limit(10, 60)
def update_leo_satellites():
    """⭐ 更新LEO卫星数量 - 轨道参数预先已知"""
    # 检查权限 - 仅管理员可修改配置
    
    data = request.get_json(silent=True)
    if data is None:
        return error_response("UNSUPPORTED_MEDIA_TYPE", "请求体必须为 application/json")
    try:
        validate_count_update(data, lo=MIN_LEO_SATELLITE_COUNT, hi=None)
    except ValidationError as ve:
        return error_response("VALIDATION_ERROR", details=ve.errors)
    new_count = data['count']
    try:
        success = simulation_engine.update_leo_satellite_count(new_count)
        
        if success:
            return jsonify({
                "success": True,
                "message": f"LEO卫星数量已更新为{new_count}颗（轨道参数预先已知，位置实时计算）",
                "leo_satellite_count": len(simulation_engine.leo_satellites),
                "satellites": [
                    {
                        "id": sat.sat_id,
                        "name": sat.name,
                        "orbit_altitude": sat.get_altitude(),
                        "orbit_period": sat.get_orbital_period()
                    }
                    for sat in simulation_engine.leo_satellites
                ]
            })
        else:
            return jsonify({
                "success": False,
                "message": "LEO卫星数量未改变"
            })
    except Exception:
        logger.exception("接口处理失败")
        return error_response("INTERNAL_ERROR")


@app.route('/api/opportunistic_stations', methods=['GET'])
def get_opportunistic_stations():
    """获取随遇接入站信息"""
    try:
        stations_info = []
        for station in OPPORTUNISTIC_STATIONS:
            # 计算当前可用波束和通道
            available_beams = station["beam_management"]["max_beams"] - len(station["current_beams"])
            available_channels = station["available_channels"]
            
            station_info = {
                "id": station["id"],
                "name": station["name"],
                "position": {
                    "lat": station["lat"],
                    "lon": station["lon"]
                },
                "type": station["type"],
                "phased_array": {
                    "elements": station["phased_array"]["elements"],
                    "beam_forming": station["phased_array"]["beam_forming"],
                    "scan_range": station["phased_array"]["scan_range"],
                    "pointing_accuracy": station["phased_array"]["pointing_accuracy"]
                },
                "beam_management": {
                    "max_beams": station["beam_management"]["max_beams"],
                    "available_beams": available_beams,
                    "beam_width": station["beam_management"]["beam_width"],
                    "interference_suppression": station["beam_management"]["interference_suppression"]
                },
                "multi_channel": {
                    "total_channels": station["multi_channel"]["channels"],
                    "available_channels": available_channels,
                    "bandwidth_per_channel": station["multi_channel"]["bandwidth_per_channel"],
                    "total_bandwidth": station["multi_channel"]["total_bandwidth"],
                    "modulation": station["multi_channel"]["modulation"]
                },
                "uplink": station["uplink"],
                "downlink": station["downlink"],
                "current_beams": station["current_beams"],
                "utilization": {
                    "beams": 1.0 - (available_beams / station["beam_management"]["max_beams"]),
                    "channels": 1.0 - (available_channels / station["multi_channel"]["channels"])
                }
            }
            stations_info.append(station_info)
        
        return jsonify({
            "success": True,
            "count": len(stations_info),
            "stations": stations_info
        })
    except Exception:
        logger.exception("接口处理失败")
        return error_response("INTERNAL_ERROR")


@app.route('/api/data_combinations', methods=['GET'])
def get_data_combinations():
    """获取数据组合维度信息"""
    try:
        return jsonify({
            "success": True,
            "total_combinations": TOTAL_DATA_COMBINATIONS,
            "base_types": list(DATA_TYPES.keys()),
            "urgency_levels": DATA_URGENCY_LEVELS,
            "qos_levels": DATA_QOS_LEVELS,
            "security_levels": DATA_SECURITY_LEVELS,
            "sample_combinations": DATA_COMBINATIONS[:10]  # 返回前10个示例
        })
    except Exception:
        logger.exception("接口处理失败")
        return error_response("INTERNAL_ERROR")



# ==========================================
# 7. 场景保存 / 加载 / 导入导出 API
# ==========================================
from backend.scenario import ScenarioManager as _ScenarioManager  # noqa: E402
from backend.store import ScenarioStore as _ScenarioStore  # noqa: E402

# 内存中保存最近一次持久化的场景（进程重启后丢失；持久化到磁盘可由外部挂载卷实现）
_saved_scene: dict | None = None

# 多场景库（内存 SQLite；生产可换为文件路径）
_scenario_store = _ScenarioStore()


@app.route('/api/scenario/save', methods=['POST'])
@require_role('admin')
@rate_limit(20, 60)
def scenario_save():
    """将当前仿真资源配置保存为场景对象并驻留内存。

    可选 JSON 体：``{"name": "我的场景"}``
    """
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", ""))[:128]  # 防止超长名称
    try:
        scene = _ScenarioManager.save(simulation_engine, name=name)
    except Exception:
        logger.exception("场景保存失败")
        return error_response("INTERNAL_ERROR")
    global _saved_scene
    _saved_scene = scene
    return ok(scene)


@app.route('/api/scenario/load', methods=['POST'])
@require_role('admin')
@rate_limit(10, 60)
def scenario_load():
    """将最近一次保存的内存场景恢复到仿真引擎。

    引擎的地面站数量和 LEO 卫星数量将被调整为场景记录值。
    """
    if _saved_scene is None:
        return error_response("NOT_FOUND", "尚未保存任何场景，请先调用 /api/scenario/save")
    try:
        result = _ScenarioManager.load(simulation_engine, _saved_scene)
    except ValueError as ve:
        return error_response("VALIDATION_ERROR", str(ve))
    except Exception:
        logger.exception("场景加载失败")
        return error_response("INTERNAL_ERROR")
    return ok(result)


@app.route('/api/scenario/export', methods=['GET'])
def scenario_export():
    """导出最近一次保存的场景为 JSON 或 YAML 文件。

    查询参数：``format=json``（默认）或 ``format=yaml``
    """
    if _saved_scene is None:
        return error_response("NOT_FOUND", "尚未保存任何场景，请先调用 /api/scenario/save")
    fmt = request.args.get("format", "json").lower().strip()
    if fmt == "yaml":
        try:
            content = _ScenarioManager.to_yaml(_saved_scene)
        except Exception:
            logger.exception("YAML 导出失败")
            return error_response("INTERNAL_ERROR")
        return app.response_class(
            response=content,
            status=200,
            mimetype="application/x-yaml",
            headers={"Content-Disposition": 'attachment; filename="scenario.yaml"'},
        )
    # 默认 JSON
    try:
        content = _ScenarioManager.to_json(_saved_scene)
    except Exception:
        logger.exception("JSON 导出失败")
        return error_response("INTERNAL_ERROR")
    return app.response_class(
        response=content,
        status=200,
        mimetype="application/json",
        headers={"Content-Disposition": 'attachment; filename="scenario.json"'},
    )


@app.route('/api/scenario/import', methods=['POST'])
@require_role('admin')
@rate_limit(10, 60)
def scenario_import():
    """从上传的 JSON 或 YAML 文本导入场景并立即还原到引擎。

    Content-Type: application/json  → JSON 解析
    Content-Type: application/x-yaml 或其他  → YAML 解析
    同时接受 multipart/form-data 中的 ``file`` 字段（前端文件上传）。
    """
    content_type = request.content_type or ""

    # 支持 multipart 文件上传
    if "multipart/form-data" in content_type:
        file = request.files.get("file")
        if file is None:
            return error_response("VALIDATION_ERROR", "multipart 请求中未找到 'file' 字段")
        raw_text = file.read(1 * 1024 * 1024).decode("utf-8", errors="replace")
        # 根据文件名后缀决定解析器
        filename = (file.filename or "").lower()
        use_yaml = filename.endswith(".yaml") or filename.endswith(".yml")
    else:
        raw_bytes = request.get_data(limit=1 * 1024 * 1024)
        raw_text = raw_bytes.decode("utf-8", errors="replace")
        use_yaml = "yaml" in content_type

    if not raw_text.strip():
        return error_response("VALIDATION_ERROR", "请求体为空")

    try:
        if use_yaml:
            scene_data = _ScenarioManager.from_yaml(raw_text)
        else:
            scene_data = _ScenarioManager.from_json(raw_text)
    except ValueError as ve:
        return error_response("VALIDATION_ERROR", f"场景解析失败: {ve}")

    errors = _ScenarioManager.validate(scene_data)
    if errors:
        return error_response("VALIDATION_ERROR", "; ".join(errors))

    try:
        result = _ScenarioManager.load(simulation_engine, scene_data)
    except ValueError as ve:
        return error_response("VALIDATION_ERROR", str(ve))
    except Exception:
        logger.exception("场景导入并还原失败")
        return error_response("INTERNAL_ERROR")

    # 成功导入后同时更新内存中保存的场景
    global _saved_scene
    _saved_scene = scene_data
    return ok(result)


@app.route('/api/scenario/current', methods=['GET'])
def scenario_current():
    """返回当前内存中保存的场景（若有）；否则返回空。"""
    return ok(_saved_scene)


# ==========================================
# 7b. 多场景库管理 API
# ==========================================

@app.route('/api/scenarios', methods=['GET'])
def scenarios_list():
    """列出场景库中全部命名场景的摘要（不含完整统计）。

    响应示例::

        {"code": 0, "data": [
          {"id": 1, "name": "基准", "saved_at": "2024-...", "is_baseline": true,
           "gs_count": 10, "leo_count": 20, "geo_count": 4},
          ...
        ]}
    """
    try:
        items = _scenario_store.list_scenarios()
    except Exception:
        logger.exception("场景库列表查询失败")
        return error_response("INTERNAL_ERROR")
    return ok(items)


@app.route('/api/scenarios', methods=['POST'])
@require_role('admin')
@rate_limit(20, 60)
def scenarios_save():
    """将当前仿真资源配置与运行统计快照保存到场景库（按名称 upsert）。

    请求体（JSON）::

        {"name": "场景名称"}   # name 必填，最长 128 字符

    响应返回完整场景记录。
    """
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()
    if not name:
        return error_response("VALIDATION_ERROR", "缺少必填字段 'name'")
    try:
        stats = simulation_engine.get_stats()
        record = _scenario_store.save_scenario(name, simulation_engine, stats)
    except ValueError as ve:
        return error_response("VALIDATION_ERROR", str(ve))
    except Exception:
        logger.exception("场景库保存失败")
        return error_response("INTERNAL_ERROR")
    return ok(record)


@app.route('/api/scenarios/<path:name>', methods=['DELETE'])
@require_role('admin')
@rate_limit(20, 60)
def scenarios_delete(name: str):
    """删除场景库中指定名称的场景。"""
    try:
        deleted = _scenario_store.delete_scenario(name)
    except Exception:
        logger.exception("场景库删除失败")
        return error_response("INTERNAL_ERROR")
    if not deleted:
        return error_response("NOT_FOUND", f"场景 '{name}' 不存在")
    return ok({"deleted": True, "name": name})


@app.route('/api/scenarios/<path:name>/activate', methods=['POST'])
@require_role('admin')
@rate_limit(10, 60)
def scenarios_activate(name: str):
    """将场景库中指定场景的资源配置应用到仿真引擎（切换场景）。"""
    try:
        result = _scenario_store.switch_to(name, simulation_engine)
    except KeyError as ke:
        return error_response("NOT_FOUND", str(ke))
    except ValueError as ve:
        return error_response("VALIDATION_ERROR", str(ve))
    except Exception:
        logger.exception("场景切换失败")
        return error_response("INTERNAL_ERROR")
    return ok(result)


@app.route('/api/scenarios/<path:name>/baseline', methods=['POST'])
@require_role('admin')
@rate_limit(10, 60)
def scenarios_set_baseline(name: str):
    """将指定场景设为基线（用于对比参考）。"""
    try:
        ok_flag = _scenario_store.set_baseline(name)
    except Exception:
        logger.exception("设置基线失败")
        return error_response("INTERNAL_ERROR")
    if not ok_flag:
        return error_response("NOT_FOUND", f"场景 '{name}' 不存在")
    return ok({"baseline": name})


@app.route('/api/scenario/compare', methods=['GET'])
def scenario_compare():
    """对比两个命名场景的决策指标，返回差值分析报告。

    查询参数：
        ``a=<场景名称A>``（必填）
        ``b=<场景名称B>``（必填）

    响应示例::

        {"code": 0, "data": {
          "scenario_a": {"name": "基准", "saved_at": "...", "is_baseline": true},
          "scenario_b": {"name": "扩容", "saved_at": "...", "is_baseline": false},
          "resource_diff": {"gs_count": {"a": 10, "b": 15, "delta": 5}, ...},
          "metrics": {
            "acceptance_rate": {"label": "接受率", "a": 0.8, "b": 0.9,
                                "delta": 0.1, "delta_pct": 12.5},
            ...
          },
          "summary": "场景 '扩容' 相对 '基准' 整体性能提升"
        }}
    """
    name_a = (request.args.get("a") or "").strip()
    name_b = (request.args.get("b") or "").strip()
    if not name_a or not name_b:
        return error_response("VALIDATION_ERROR", "必须通过查询参数 a 和 b 指定两个场景名称")
    try:
        report = _scenario_store.compare(name_a, name_b)
    except KeyError as ke:
        return error_response("NOT_FOUND", str(ke))
    except Exception:
        logger.exception("场景对比失败")
        return error_response("INTERNAL_ERROR")
    return ok(report)


# ==========================================
# 8b. TLE 导入与缓存 API
# ==========================================
from backend.physics.tle_source import (  # noqa: E402
    fetch_group,
    fetch_by_catnr,
    get_cache_status,
    inject_tle_into_constellation,
    SUPPORTED_GROUPS,
)


@app.route('/api/tle/import', methods=['POST'])
@require_role('admin')
@rate_limit(5, 60)
def tle_import():
    """从 Celestrak 导入指定分组或编号的 TLE 星历并缓存到本地。

    请求体（JSON）::

        {
            "group": "starlink",      # 星座分组名，与 catnr 二选一
            "catnr": 25544,           # NORAD 卫星编号，与 group 二选一
            "force_refresh": false,   # 是否强制刷新（可选，默认 false）
            "inject": false           # 是否将 TLE 注入仿真引擎星座（可选，默认 false）
        }

    响应示例::

        {"code": 0, "data": {
            "group": "starlink",
            "entry_count": 6000,
            "injected": 12,
            "first_epoch": "2024-05-01T00:00:00Z",
            "cached_at": "2024-05-01T12:00:00Z"
        }}
    """
    body = request.get_json(silent=True) or {}
    group = str(body.get("group", "")).strip()
    catnr = body.get("catnr")
    force_refresh = bool(body.get("force_refresh", False))
    do_inject = bool(body.get("inject", False))

    if not group and catnr is None:
        return error_response("VALIDATION_ERROR", "必须提供 'group'（星座名）或 'catnr'（NORAD 编号）之一")

    try:
        if catnr is not None:
            try:
                catnr_int = int(catnr)
            except (TypeError, ValueError):
                return error_response("VALIDATION_ERROR", "'catnr' 必须为整数")
            entries = fetch_by_catnr(catnr_int, force_refresh=force_refresh)
            used_group = f"catnr_{catnr_int}"
        else:
            entries = fetch_group(group, force_refresh=force_refresh)
            used_group = group

        injected = 0
        if do_inject and entries:
            with simulation_engine.lock:
                sats = list(simulation_engine.leo_satellites) + list(simulation_engine.meo_satellites)
            injected = inject_tle_into_constellation(entries, sats)

        first_epoch = entries[0][3] if entries else ""
        return ok({
            "group": used_group,
            "entry_count": len(entries),
            "injected": injected,
            "first_epoch": first_epoch,
            "supported_groups": SUPPORTED_GROUPS,
        })
    except Exception:
        logger.exception("TLE 导入失败")
        return error_response("INTERNAL_ERROR")


@app.route('/api/tle/status', methods=['GET'])
def tle_status():
    """查看本地 TLE 缓存的新鲜度与条目统计。

    响应示例::

        {"code": 0, "data": {
            "cache_dir": "/path/to/data/tle_cache",
            "total_groups": 3,
            "total_tles": 18000,
            "entries": [
                {"group": "starlink", "fetched_at": "...", "age_seconds": 300,
                 "is_fresh": true, "entry_count": 6000}
            ],
            "supported_groups": [...]
        }}
    """
    try:
        status = get_cache_status()
        status["supported_groups"] = SUPPORTED_GROUPS
        return ok(status)
    except Exception:
        logger.exception("TLE 状态查询失败")
        return error_response("INTERNAL_ERROR")


# ==========================================
# 9. 仿真快照 / 回放 API
# ==========================================
from backend.snapshot import SnapshotManager as _SnapshotManager  # noqa: E402

# 内存中保存最近一次的快照（进程重启后丢失；持久化可通过外部存储实现）
_saved_snapshot: dict | None = None


@app.route('/api/snapshot/save', methods=['POST'])
@require_role('admin')
@rate_limit(20, 60)
def snapshot_save():
    """拍摄当前仿真状态快照并保存至内存。

    可选 JSON 体：``{"label": "回放点A"}``

    返回快照摘要（不含完整请求列��以减小响应体积）。
    """
    body = request.get_json(silent=True) or {}
    label = str(body.get("label", ""))[:128]
    try:
        snap = simulation_engine.snapshot(label=label)
    except Exception:
        logger.exception("快照保存失败")
        return error_response("INTERNAL_ERROR")

    global _saved_snapshot
    _saved_snapshot = snap

    # 响应中仅返回摘要，完整快照可通过 /api/snapshot/export 下载
    return ok({
        "version": snap["version"],
        "saved_at": snap["saved_at"],
        "label": snap.get("label", ""),
        "current_time": snap["current_time"],
        "id_counter": snap.get("id_counter", 0),
        "active_request_count": len(snap.get("transmission_requests", [])),
        "history_count": len(snap.get("request_history", [])),
    })


@app.route('/api/snapshot/load', methods=['POST'])
@require_role('admin')
@rate_limit(10, 60)
def snapshot_load():
    """将最���一次保存的快照恢复到仿真引擎，进入回放模式。

    回放模式下主仿真循环暂停，/api/data 返回快照时刻的态势数据。
    调用 /api/snapshot/resume 可退出回放模式，重启仿真。
    """
    if _saved_snapshot is None:
        return error_response("NOT_FOUND", "尚未保存任何快照，请先调用 /api/snapshot/save")
    try:
        result = simulation_engine.restore(_saved_snapshot)
    except ValueError as ve:
        return error_response("VALIDATION_ERROR", str(ve))
    except Exception:
        logger.exception("快照恢复失败")
        return error_response("INTERNAL_ERROR")
    return ok(result)


@app.route('/api/snapshot/resume', methods=['POST'])
@require_role('admin')
@rate_limit(10, 60)
def snapshot_resume():
    """退出回放模式，重启主仿真循环。"""
    restarted = simulation_engine.resume_from_snapshot()
    return ok({
        "restarted": restarted,
        "simulation_running": simulation_engine.running,
    })


@app.route('/api/snapshot/status', methods=['GET'])
def snapshot_status():
    """返回当前快照与回放状态摘要。"""
    replay_mode = getattr(simulation_engine, '_replay_mode', False)
    if _saved_snapshot is not None:
        snap_summary = {
            "available": True,
            "saved_at": _saved_snapshot.get("saved_at", ""),
            "label": _saved_snapshot.get("label", ""),
            "current_time": _saved_snapshot.get("current_time", 0),
            "active_request_count": len(_saved_snapshot.get("transmission_requests", [])),
            "history_count": len(_saved_snapshot.get("request_history", [])),
        }
    else:
        snap_summary = {"available": False}

    return ok({
        "replay_mode": replay_mode,
        "simulation_running": simulation_engine.running,
        "snapshot": snap_summary,
    })


@app.route('/api/snapshot/export', methods=['GET'])
def snapshot_export():
    """将内存中的快照以 JSON 文件形式下载。"""
    if _saved_snapshot is None:
        return error_response("NOT_FOUND", "尚未保存任何快照，请先调用 /api/snapshot/save")
    try:
        content = _SnapshotManager.to_json(_saved_snapshot)
    except Exception:
        logger.exception("快照导出失败")
        return error_response("INTERNAL_ERROR")
    label = (_saved_snapshot.get("label") or "snapshot").replace(" ", "_")[:32]
    filename = f"{label}.snapshot.json"
    return app.response_class(
        response=content,
        status=200,
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.route('/api/snapshot/import', methods=['POST'])
@require_role('admin')
@rate_limit(10, 60)
def snapshot_import():
    """从上传的 JSON 文件导入快照并立即恢复仿真状态。

    Content-Type: application/json  → JSON 解析
    同时接受 multipart/form-data 中的 ``file`` 字段（前端文件上传）。
    """
    content_type = request.content_type or ""

    if "multipart/form-data" in content_type:
        file = request.files.get("file")
        if file is None:
            return error_response("VALIDATION_ERROR", "multipart 请求中未找到 'file' 字段")
        raw_text = file.read(4 * 1024 * 1024).decode("utf-8", errors="replace")
    else:
        raw_bytes = request.get_data()
        raw_text = raw_bytes.decode("utf-8", errors="replace")

    if not raw_text.strip():
        return error_response("VALIDATION_ERROR", "请求体为空")

    try:
        snap_data = _SnapshotManager.from_json(raw_text)
    except ValueError as ve:
        return error_response("VALIDATION_ERROR", f"快照解析失败: {ve}")

    errors = _SnapshotManager.validate(snap_data)
    if errors:
        return error_response("VALIDATION_ERROR", "; ".join(errors))

    try:
        result = simulation_engine.restore(snap_data)
    except ValueError as ve:
        return error_response("VALIDATION_ERROR", str(ve))
    except Exception:
        logger.exception("快照导入恢复失败")
        return error_response("INTERNAL_ERROR")

    global _saved_snapshot
    _saved_snapshot = snap_data
    return ok(result)


# ==========================================
# 8. Static frontend and open metadata routes
# ==========================================

@app.route('/')
def index():
    """Serve the separated frontend shell."""
    return send_from_directory(FRONTEND_DIR, 'index.html')


@app.route('/frontend/')
def frontend_index():
    return send_from_directory(FRONTEND_DIR, 'index.html')


@app.route('/frontend/<path:filename>')
def frontend_assets(filename):
    return send_from_directory(FRONTEND_DIR, filename)


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """账号密码登录，签发 access/refresh JWT。"""
    data = request.get_json(silent=True) or {}
    role = authenticate_user(data.get('username'), data.get('password'))
    if not role:
        return error_response("UNAUTHORIZED", "用户名或密码错误")
    sub = data.get('username')
    return jsonify({
        'token_type': 'Bearer',
        'access_token': create_access_token(sub, role),
        'refresh_token': create_refresh_token(sub, role),
        'role': role,
    })


@app.route('/api/auth/refresh', methods=['POST'])
def auth_refresh():
    """用 refresh token 换取新的 access token。"""
    data = request.get_json(silent=True) or {}
    token = data.get('refresh_token')
    try:
        claims = decode_token(token) if token else None
        if not claims or claims.get('type') != 'refresh':
            raise ValueError("not a refresh token")
    except (_jwt.PyJWTError, ValueError):
        return error_response("UNAUTHORIZED", "刷新令牌无效或已过期")
    return jsonify({
        'token_type': 'Bearer',
        'access_token': create_access_token(claims.get('sub'), claims.get('role', 'viewer')),
    })


# 角色 -> 权限映射（RBAC 由后续 PR 进一步细化与强制）
_ROLE_PERMISSIONS = {
    'admin': {'can_submit_request': True, 'can_modify_config': True},
    'operator': {'can_submit_request': True, 'can_modify_config': False},
    'viewer': {'can_submit_request': False, 'can_modify_config': False},
}


@app.route('/api/user_info')
def get_user_info():
    """返回当前令牌身份与角色对应的权限。"""
    ident = getattr(g, 'identity', {}) or {}
    role = ident.get('role', 'operator')
    sub = ident.get('sub') or ('open-operator' if ident.get('auth') == 'open' else role)
    perms = _ROLE_PERMISSIONS.get(role, _ROLE_PERMISSIONS['viewer'])
    return ok({
        'username': sub,
        'role': role,
        'display_name': sub,
        'auth_mode': ident.get('auth', 'open'),
        'permissions': perms,
    })


@app.route('/api/health')
def health_check():
    return jsonify({
        'success': True,
        'service': 'smartnode-backend',
        'version': __version__,
        'mode': 'open-api',
        'frontend': '/frontend/',
        'simulation_running': simulation_engine.running
    })


@app.route('/api/livez')
def liveness_probe():
    """存活探针：进程可响应即存活。"""
    return jsonify({'status': 'alive'})


@app.route('/api/readyz')
@app.route('/api/ready')
def readiness_probe():
    """就绪探针：仿真线程存活才视为就绪，否则 503。

    同时挂载 /api/ready（K8s / Compose 约定俗成的短路径）与 /api/readyz。
    校验逻辑：仿真引擎 running 标志为真且后台线程存活，才认为服务就绪。
    非就绪时返回 HTTP 503，供 K8s livenessProbe / readinessProbe 与
    Alertmanager dead_man_switch 规则使用。
    """
    thread = simulation_engine.simulation_thread
    thread_alive = bool(thread and thread.is_alive())
    ready = bool(simulation_engine.running and thread_alive)
    body = {
        'status': 'ready' if ready else 'not_ready',
        'simulation_running': simulation_engine.running,
        'simulation_thread_alive': thread_alive,
        'version': __version__,
    }
    return (jsonify(body), 200) if ready else (jsonify(body), 503)


@app.route('/api/quota')
def quota_status():
    """返回当前身份的限流配额信息（用于客户端自适应退避）。"""
    ident = getattr(g, 'identity', {}) or {}
    return ok({
        'identity': ident.get('sub') or ident.get('auth', 'open'),
        'limits': {
            'submit_request': {'limit': 30, 'window_seconds': 60},
            'update_config': {'limit': 10, 'window_seconds': 60},
        },
    })


@app.route('/favicon.ico')
def favicon():
    """返回空favicon避免404错误"""
    return '', 204


@app.route('/api/openapi.json')
def openapi_spec():
    """OpenAPI 3.1 规范（机器可读）。"""
    return jsonify(OPENAPI_SPEC)


@app.route('/docs')
def swagger_docs():
    """Swagger UI 文档站。"""
    return SWAGGER_HTML, 200, {'Content-Type': 'text/html; charset=utf-8'}


# ==========================================
# 调度决策轨迹 API
# ==========================================

@app.route('/api/decision_trace', methods=['GET'])
def get_decision_traces():
    """返回所有调度决策轨迹记录（有限长度环形缓冲，最多 500 条）。

    可选查询参数：
      - limit (int): 最多返回最近 N 条轨迹（默认返回全部）
      - outcome (str): 按结果过滤，可取 "scheduled"、"rejected"、"rerouted"

    返回 JSON 结构：
      {
        "total": <缓冲中总条数>,
        "buffer_max": <缓冲上限>,
        "traces": [ { ...DecisionTrace 字段... }, ... ]
      }
    """
    with simulation_engine.lock:
        buf = simulation_engine.decision_trace_buffer
        traces = buf.list_all()

    # 可选：按 outcome 过滤
    outcome_filter = request.args.get("outcome")
    if outcome_filter:
        traces = [t for t in traces if t.outcome == outcome_filter]

    # 可选：限制返回条数（取最近 N 条）
    limit_str = request.args.get("limit")
    if limit_str is not None:
        try:
            limit = int(limit_str)
            if limit < 1:
                return error_response("INVALID_PARAM", "limit 必须为正整数"), 400
            traces = traces[-limit:]
        except ValueError:
            return error_response("INVALID_PARAM", "limit 必须为整数"), 400

    return jsonify(ok({
        "total": len(simulation_engine.decision_trace_buffer),
        "buffer_max": simulation_engine.decision_trace_buffer.maxlen,
        "traces": [t.to_dict() for t in traces],
    }))


@app.route('/api/decision_trace/<string:req_id>', methods=['GET'])
def get_decision_trace_by_id(req_id):
    """按请求 ID 查询单条调度决策轨迹。

    路径参数：
      - req_id: 请求 ID，如 "REQ_0001"

    成功返回 200 + 轨迹 JSON；
    未找到时返回 404 + 标准化错误。
    """
    with simulation_engine.lock:
        buf = simulation_engine.decision_trace_buffer
        trace = buf.get(req_id)

    if trace is None:
        return error_response(
            "NOT_FOUND",
            f"未找到请求 {req_id!r} 的决策轨迹（可能已超出环形缓冲上限或尚未被调度）"
        ), 404

    return jsonify(ok(trace.to_dict()))


# ==========================================
# 接口版本化：为每个 /api/<x> 注册 /api/v1/<x> 别名（保留旧路径兼容）
# ==========================================
def _register_v1_aliases():
    existing = list(app.url_map.iter_rules())
    for rule in existing:
        path = str(rule.rule)
        if path.startswith('/api/') and not path.startswith('/api/v1/'):
            view = app.view_functions[rule.endpoint]
            methods = sorted(m for m in rule.methods if m in {'GET', 'POST', 'PUT', 'DELETE', 'PATCH'})
            app.add_url_rule('/api/v1/' + path[len('/api/'):], endpoint='v1_' + rule.endpoint,
                             view_func=view, methods=methods)


_register_v1_aliases()


def run(host: str | None = None, port: int | None = None, debug: bool = False) -> None:
    """启动 Flask 开发服务器。

    host / port 优先使用调用方传入的值；未传入时读取环境变量
    （SMARTNODE_HOST / SMARTNODE_PORT），最终回退到历史默认值。
    """
    _host = host if host is not None else get_bind_host()
    _port = port if port is not None else get_bind_port()
    validate_config()  # 生产模式下缺失必填密钥即拒启
    simulation_engine.reset_requests()
    app.run(debug=debug, host=_host, port=_port, use_reloader=False, threaded=True)


if __name__ == '__main__':
    print('=' * 60)
    print('天基智枢 SmartNode 仿真平台启动中...')
    _h = get_bind_host()
    _p = get_bind_port()
    print(f'访问地址: http://{_h}:{_p}/frontend/')
    print('=' * 60)
    try:
        run()
    except Exception as e:
        import traceback
        logger.error(
            "Flask 服务启动异常",
            error=str(e),
            traceback=traceback.format_exc(),
        )
