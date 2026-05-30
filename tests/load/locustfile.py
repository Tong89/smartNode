# -*- coding: utf-8 -*-
"""Locust 负载测试文件：对 SmartNode /api/request 接口进行阶梯加压。

用法::

    # 安装: pip install locust
    # 启动 headless 模式（100 用户，爬坡 10 用户/秒，持续 60 秒）
    locust -f tests/load/locustfile.py --headless -u 100 -r 10 -t 60s \
           --host http://localhost:5000

    # 交互式 Web UI 模式
    locust -f tests/load/locustfile.py --host http://localhost:5000

环境变量::

    LOAD_DATA_TYPE   - 请求使用的数据类型（默认 TASK_CMD）
    LOAD_PRIORITY    - 请求优先级 1-10（默认 5）
    LOAD_MAX_DELAY   - 最大允许延迟秒数（默认 600）
"""

import os
import random
import json

try:
    from locust import HttpUser, task, between, events
except ImportError:
    raise ImportError(
        "locust 未安装，请运行: pip install locust\n"
        "或安装开发依赖: pip install -r requirements-dev.txt"
    )

# ---------------------------------------------------------------------------
# 可配置参数（通过环境变量覆盖）
# ---------------------------------------------------------------------------

_DATA_TYPES = ["TASK_CMD", "INTEL", "DATA_SLICE", "RAW_IMAGE", "TELEMETRY"]

_DEFAULT_DATA_TYPE = os.getenv("LOAD_DATA_TYPE", "TASK_CMD")
_DEFAULT_PRIORITY = int(os.getenv("LOAD_PRIORITY", "5"))
_DEFAULT_MAX_DELAY = int(os.getenv("LOAD_MAX_DELAY", "600"))


def _random_payload() -> dict:
    """生成随机但结构合法的请求载荷。"""
    data_type = random.choice(_DATA_TYPES)
    return {
        "data_type": data_type,
        "data_size": random.randint(10, 5000),
        "priority": random.randint(1, 10),
        "max_delay": random.choice([300, 600, 900, 1800]),
    }


def _fixed_payload(data_type: str = _DEFAULT_DATA_TYPE,
                   priority: int = _DEFAULT_PRIORITY,
                   max_delay: int = _DEFAULT_MAX_DELAY) -> dict:
    """生成固定类型的请求载荷，用于场景化压测。"""
    return {
        "data_type": data_type,
        "data_size": 100,
        "priority": priority,
        "max_delay": max_delay,
    }


# ---------------------------------------------------------------------------
# 用户行为定义
# ---------------------------------------------------------------------------

class SmartNodeUser(HttpUser):
    """模拟普通用户提交传输请求。

    等待时间 0.1-1.0 秒，模拟真实用户操作间隔。
    """

    wait_time = between(0.1, 1.0)

    @task(5)
    def submit_fixed_request(self):
        """高权重：提交固定类型（TASK_CMD/高优先级）的请求。"""
        payload = _fixed_payload()
        with self.client.post(
            "/api/request",
            json=payload,
            catch_response=True,
            name="/api/request[fixed]",
        ) as resp:
            if resp.status_code not in (200, 400, 429):
                resp.failure(f"Unexpected status: {resp.status_code}")
            else:
                resp.success()

    @task(3)
    def submit_random_request(self):
        """中权重：提交随机类型请求，覆盖多种数据类型。"""
        payload = _random_payload()
        with self.client.post(
            "/api/request",
            json=payload,
            catch_response=True,
            name="/api/request[random]",
        ) as resp:
            if resp.status_code not in (200, 400, 429):
                resp.failure(f"Unexpected status: {resp.status_code}")
            else:
                resp.success()

    @task(1)
    def submit_low_priority_request(self):
        """低权重：提交低优先级请求，压力测试下预期会被拒绝。"""
        payload = _fixed_payload(data_type="DATA_SLICE", priority=1)
        with self.client.post(
            "/api/request",
            json=payload,
            catch_response=True,
            name="/api/request[low_priority]",
        ) as resp:
            if resp.status_code not in (200, 400, 429):
                resp.failure(f"Unexpected status: {resp.status_code}")
            else:
                resp.success()

    @task(1)
    def check_health(self):
        """轮询健康检查接口，监控系统在高负载下的响应能力。"""
        with self.client.get("/api/health", catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"Health check failed: {resp.status_code}")
            else:
                body = resp.json()
                if body.get("status") != "ok":
                    resp.failure("Health status not ok")
                else:
                    resp.success()

    @task(1)
    def check_system_info(self):
        """轮询系统信息接口，监控统计计数。"""
        self.client.get("/api/system_info", name="/api/system_info")

    @task(1)
    def check_resource_utilization(self):
        """轮询资源利用率接口，采集基线数据。"""
        self.client.get("/api/resource_utilization", name="/api/resource_utilization")


class HighConcurrencyUser(HttpUser):
    """模拟高并发爆发场景：极短等待，连续提交请求。

    用于压力测试下检验引擎的拒绝行为与统计计数守恒。
    """

    wait_time = between(0.01, 0.1)

    @task
    def burst_submit(self):
        """高频提交 TASK_CMD 请求，制造峰值并发压力。"""
        payload = {
            "data_type": "TASK_CMD",
            "data_size": 50,
            "priority": random.randint(3, 9),
            "max_delay": 300,
        }
        with self.client.post(
            "/api/request",
            json=payload,
            catch_response=True,
            name="/api/request[burst]",
        ) as resp:
            if resp.status_code not in (200, 400, 429):
                resp.failure(f"Unexpected burst status: {resp.status_code}")
            else:
                resp.success()


# ---------------------------------------------------------------------------
# 测试事件钩子：打印摘要
# ---------------------------------------------------------------------------

@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    """测试结束时输出关键指标摘要到控制台。"""
    stats = environment.runner.stats
    total = stats.total
    print("\n" + "=" * 60)
    print("负载测试摘要 / Load Test Summary")
    print("=" * 60)
    print(f"总请求数   : {total.num_requests}")
    print(f"失败请求数 : {total.num_failures}")
    print(f"平均响应时  : {total.avg_response_time:.1f} ms")
    print(f"P95 响应时  : {total.get_response_time_percentile(0.95):.1f} ms")
    print(f"P99 响应时  : {total.get_response_time_percentile(0.99):.1f} ms")
    print(f"峰值 RPS    : {total.max_rps:.1f}")
    print("=" * 60)
