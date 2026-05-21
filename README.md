# 天基智枢 SmartNode

> Space-Based Intelligent Relay Simulation Platform

天基智枢 SmartNode 是一个面向天基数据回传场景的可视化仿真平台，用于演示 LEO/MEO/GEO 卫星、地面站、中继链路和内容驱动任务调度之间的协同关系。

项目已调整为前后端分离结构，后端提供开放 API，前端作为独立静态控制台运行，适合开源展示、二次开发和算法实验。

## 特性

- 三维空间态势展示：基于 Cesium 展示卫星、地面站、中继星和活动链路。
- 内容驱动任务提交：支持不同数据类型、优先级、时延约束和指定资源。
- 资源状态观测：展示卫星、地面站、中继资源的实时占用和综合利用率。
- 开放 API 模式：已移除密码登录、角色权限和改密逻辑，便于开源部署。
- 轻量前端：Vue 3 + Cesium + 原生 CSS，无构建步骤即可运行。

## 项目结构

```text
smartNode/
├─ backend/
│  ├─ __init__.py
│  └─ app.py              # 后端入口
├─ frontend/
│  ├─ assets/
│  │  └─ world.jpg
│  ├─ app.js              # 前端交互逻辑
│  ├─ index.html          # 前端页面
│  └─ styles.css          # 全新 UI 样式
├─ main.py                # 仿真引擎与 Flask API 兼容层
├─ start.py               # 桌面/浏览器启动入口
├─ run_server.bat         # Windows 启动脚本
├─ restart_server.ps1     # Windows 重启脚本
├─ requirements.txt
└─ README.md
```

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/Tong89/smartNode.git
cd smartNode
```

### 2. 安装依赖

```bash
python -m venv .venv
```

Windows:

```powershell
.\.venv\Scripts\activate
pip install -r requirements.txt
```

macOS / Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

如果需要 `python start.py` 打开桌面窗口，可以额外安装：

```bash
pip install -r requirements-desktop.txt
```

### 3. 启动后端

```bash
python backend/app.py
```

访问前端：

```text
http://127.0.0.1:5000/frontend/
```

健康检查：

```text
http://127.0.0.1:5000/api/health
```

## 常用 API

| 方法 | 地址 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 服务健康检查 |
| GET | `/api/data` | 获取完整仿真态势数据 |
| GET | `/api/system_info` | 获取系统配置和数据类型 |
| GET | `/api/resource_status` | 获取实时资源状态 |
| GET | `/api/resource_utilization` | 获取资源利用率统计 |
| POST | `/api/request` | 提交数据回传任务 |
| POST | `/api/update_ground_stations` | 调整地面站数量 |
| POST | `/api/update_leo_satellites` | 调整 LEO 卫星数量 |

提交任务示例：

```bash
curl -X POST http://127.0.0.1:5000/api/request \
  -H "Content-Type: application/json" \
  -d '{"data_type":"DATA_SLICE","data_size":120,"priority":5,"max_delay":600}'
```

## 前后端分离部署

默认情况下，Flask 会托管 `frontend/` 静态页面：

```text
http://127.0.0.1:5000/frontend/
```

如果你希望真正分成两个服务，可以用任意静态服务器托管 `frontend/`，然后在页面右上角 API Base 输入后端地址，例如：

```text
http://127.0.0.1:5000
```

## 开发检查

```bash
python -m py_compile main.py backend/app.py start.py
node --check frontend/app.js
```

## 路线图

- 将 `main.py` 中的仿真模型、调度算法和 Flask 路由继续拆分到 `backend/` 子模块。
- 增加后端 API 单元测试。
- 增加任务调度策略插件化能力。
- 增加数据导出和实验复现实例。

## 许可证

本项目基于 MIT License 开源，详见 [LICENSE](LICENSE)。
