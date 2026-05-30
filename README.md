# 天基智枢 SmartNode

> Space-Based Intelligent Relay Simulation Platform

[![CI](https://github.com/Tong89/smartNode/actions/workflows/ci.yml/badge.svg)](https://github.com/Tong89/smartNode/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-60%25%20min-brightgreen)](https://github.com/Tong89/smartNode/actions/workflows/ci.yml)

天基智枢 SmartNode 是一个面向天基数据回传场景的可视化仿真平台，用于展示卫星、地面站、中继链路和内容驱动任务调度之间的协同关系。

## 功能

- 三维空间态势展示
- 数据回传任务提交
- 卫星、地面站、中继资源状态监测
- 实时资源利用率统计
- 前后端分离结构
- 开放 API，无密码登录依赖

## 目录结构

```text
smartNode/
├─ backend/
│  ├─ __init__.py
│  ├─ app.py          # 后端启动入口
│  ├─ api.py          # Flask API 和静态页面托管
│  └─ core.py         # 仿真模型、配置和调度引擎
├─ frontend/
│  ├─ assets/
│  ├─ app.js
│  ├─ index.html
│  └─ styles.css
├─ main.py            # 兼容入口
├─ run_server.bat     # Windows 快速启动脚本
├─ requirements.in        # 运行时直接依赖（source constraints）
├─ requirements.txt       # 锁定的运行时依赖（pip-compile 生成，含哈希）
├─ requirements-dev.in    # 开发依赖（source constraints）
├─ requirements-dev.txt   # 锁定的开发依赖（pip-compile 生成，含哈希）
├─ LICENSE
└─ README.md
```

## 依赖管理

本项目使用 [pip-tools](https://github.com/jazzband/pip-tools) 管理可复现的依赖树：

| 文件 | 说明 |
| --- | --- |
| `requirements.in` | 运行时直接依赖（人工维护的 source constraints） |
| `requirements.txt` | 锁定的运行时依赖（由 `pip-compile` 自动生成，含 SHA-256 哈希） |
| `requirements-dev.in` | 开发/测试直接依赖（source constraints，包含 `-r requirements.in`） |
| `requirements-dev.txt` | 锁定的开发依赖（由 `pip-compile` 自动生成，含 SHA-256 哈希） |

**更新依赖版本：**

```bash
pip install pip-tools

# 仅更新运行时依赖
pip-compile --generate-hashes requirements.in

# 更新开发依赖（会同时拉取最新运行时依赖）
pip-compile --generate-hashes requirements-dev.in
```

> **注意**：永远不要手动编辑 `requirements.txt` 或 `requirements-dev.txt`。
> 请修改对应的 `.in` 文件，然后重新运行 `pip-compile` 生成锁定文件。

## 快速开始

```bash
git clone https://github.com/Tong89/smartNode.git
cd smartNode
python -m venv .venv
```

Windows:

```powershell
.\.venv\Scripts\activate
pip install -r requirements.txt
python backend/app.py
```

macOS / Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
python backend/app.py
```

访问：

```text
http://127.0.0.1:5000/frontend/
```

Windows 也可以直接双击：

```text
run_server.bat
```

## 常用 API

| 方法 | 地址 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/data` | 仿真态势数据 |
| GET | `/api/system_info` | 系统配置和数据类型 |
| GET | `/api/resource_status` | 实时资源状态 |
| GET | `/api/resource_utilization` | 资源利用率统计 |
| POST | `/api/request` | 提交数据回传任务 |
| POST | `/api/update_ground_stations` | 调整地面站数量 |
| POST | `/api/update_leo_satellites` | 调整 LEO 卫星数量 |

## 开发检查

```bash
python -m py_compile main.py backend/app.py backend/api.py backend/core.py
node --check frontend/app.js
```

## 测试与覆盖率

安装开发依赖并运行测试套件（与 CI 保持一致）：

```bash
pip install -r requirements-dev.txt

# 运行全部测试
pytest

# 运行测试并生成覆盖率报告（阈值 60%，低于则失败）
pytest --cov=backend --cov-config=.coveragerc --cov-report=term-missing --cov-fail-under=60

# 输出 HTML 报告（可用浏览器查看）
pytest --cov=backend --cov-config=.coveragerc --cov-report=html
open htmlcov/index.html
```

CI 工作流（`.github/workflows/ci.yml`）会在 Python 3.10、3.11、3.12 上并行执行上述步骤，并将 `coverage.xml` 作为工件上传，供后续分析使用。覆盖率低于门禁阈值时 CI 显式失败。

## 说明

- 当前版本适合本地仿真、教学展示和二次开发。
- 如需公网部署，请在网关层增加认证、限流和访问控制。

## License

MIT License. See [LICENSE](LICENSE).
