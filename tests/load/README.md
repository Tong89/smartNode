# SmartNode 调度引擎负载与压力测试套件

本目录包含针对 `SimulationEngine` 的负载测试与压力测试脚本，分为两个层次：

1. **`test_stress_engine.py`** — 纯 Python 压测（直接驱动引擎，无需 HTTP 服务器）
2. **`locustfile.py`** — HTTP 接口负载测试（需要运行后端服务）

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements-dev.txt
# 若需运行 locust HTTP 负载测试，额外安装：
pip install locust
```

### 2. 运行纯 Python 压测（推荐先跑此项）

```bash
# 在项目根目录运行
pytest tests/load/test_stress_engine.py -v

# 显示负载基线摘要（含拒绝原因分布与吞吐统计）
pytest tests/load/test_stress_engine.py -v -s

# 只运行并发测试
pytest tests/load/test_stress_engine.py -v -k "concurrent"

# 只运行统计守恒测试
pytest tests/load/test_stress_engine.py -v -k "Consistency"
```

### 3. 运行 Locust HTTP 负载测试

首先启动后端服务：

```bash
python main.py
```

然后在另一个终端：

```bash
# 交互式 Web UI（访问 http://localhost:8089）
locust -f tests/load/locustfile.py --host http://localhost:5000

# Headless 模式（100 用户，爬坡 10 用户/秒，持续 60 秒）
locust -f tests/load/locustfile.py --headless -u 100 -r 10 -t 60s \
       --host http://localhost:5000

# 高并发压力测试（500 用户）
locust -f tests/load/locustfile.py --headless -u 500 -r 50 -t 120s \
       --host http://localhost:5000
```

---

## 测试场景说明

### `test_stress_engine.py` 测试类

| 测试类 | 验证目标 |
|--------|---------|
| `TestNoUncaughtExceptions` | 阶梯加压（10/50/200 请求），引擎无未捕获异常 |
| `TestRejectionReasonDistribution` | 拒绝原因属于已知集合，分布合理 |
| `TestStatsConsistency` | `total == accepted + rejected` 守恒 |
| `TestRequestHistoryGrowth` | `request_history` 长度 <= 总提交次数 |
| `TestThroughputAndSummary` | 打印吞吐摘要供基线参考 |
| `TestHighUtilizationBehavior` | 步进推进 + 高占用下行为稳定 |

### `locustfile.py` 用户类型

| 用户类型 | 描述 |
|---------|------|
| `SmartNodeUser` | 模拟普通用户：固定/随机请求混合，等待 0.1-1.0 秒 |
| `HighConcurrencyUser` | 高并发爆发：极短等待（0.01-0.1 秒），连续提交 |

---

## 可配置环境变量（Locust）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LOAD_DATA_TYPE` | `TASK_CMD` | 固定类型请求使用的数据类型 |
| `LOAD_PRIORITY` | `5` | 请求优先级（1-10） |
| `LOAD_MAX_DELAY` | `600` | 最大允许延迟（秒） |

示例：

```bash
LOAD_DATA_TYPE=DATA_SLICE LOAD_PRIORITY=2 \
  locust -f tests/load/locustfile.py --headless -u 200 -r 20 -t 60s \
         --host http://localhost:5000
```

---

## 验收标准

- [x] 压测脚本可配置并发与时长运行（通过 `-u`/`-r`/`-t` 参数或环境变量）
- [x] 高负载下引擎无未捕获异常（`TestNoUncaughtExceptions` 全部通过）
- [x] 统计计数自洽（`TestStatsConsistency` 全部通过）
- [x] 拒绝原因归属已知集合（`TestRejectionReasonDistribution` 全部通过）
- [x] 输出拒绝原因分布与吞吐摘要供基线参考（`test_print_load_summary` 打印摘要）

---

## 典型输出示例

```
负载测试基线摘要 (Load Baseline Summary)
========================================================
  提交总数     : 200
  接受数       : 178
  拒绝数       : 22
  接受率       : 89.0%
  拒绝原因分布 :
    NO_VISIBLE_RELAY                    : 14
    BANDWIDTH_EXCEEDED                  : 5
    SATELLITE_OVERLOAD                  : 3
========================================================
```
