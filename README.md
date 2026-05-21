# 天基智枢 SmartNode

> Space-Based Intelligent Relay Simulation Platform

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
├─ requirements.txt
├─ LICENSE
└─ README.md
```

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

## 说明

- 当前版本适合本地仿真、教学展示和二次开发。
- 不建议直接把开发服务器暴露到公网。
- 如需公网部署，请在网关层增加认证、限流和访问控制。

## License

MIT License. See [LICENSE](LICENSE).
