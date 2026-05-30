# -*- coding: utf-8 -*-
"""Flask API and static frontend routes for SmartNode."""

import logging
import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from flask import g

from backend.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    decode_token,
    init_auth,
)
from backend.config import GS_MAX_BANDWIDTH, SATELLITE_MAX_BANDWIDTH, debug_api_enabled, validate_config
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

logger = logging.getLogger("smartnode")

app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False
# 限制请求体大小，防止超大 payload 耗尽资源
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024  # 1 MB

# 注册统一脱敏错误处理器（4xx/5xx 返回稳定错误码，不回传 traceback）
register_error_handlers(app)

# 注册可插拔 API Key 鉴权（未配置 SMARTNODE_API_KEY 时降级为开放模式）
init_auth(app)


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
# 7. Static frontend and open metadata routes
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
        'mode': 'open-api',
        'frontend': '/frontend/',
        'simulation_running': simulation_engine.running
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


def run(host='127.0.0.1', port=5000, debug=False):
    validate_config()  # 生产模式下缺失必填密钥即拒启
    simulation_engine.reset_requests()
    app.run(debug=debug, host=host, port=port, use_reloader=False, threaded=True)


if __name__ == '__main__':
    print('=' * 60)
    print('天基智枢 SmartNode 仿真平台启动中...')
    print('访问地址: http://127.0.0.1:5000/frontend/')
    print('=' * 60)
    try:
        run()
    except Exception as e:
        print(f'[FATAL] Flask 服务异常: {e}')
        import traceback
        traceback.print_exc()
