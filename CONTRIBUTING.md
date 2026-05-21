# Contributing

感谢你关注天基智枢 SmartNode。

## 开发流程

1. Fork 本仓库并创建特性分支。
2. 保持改动聚焦，避免混入无关格式化。
3. 提交前运行基础检查：

```bash
python -m py_compile main.py backend/app.py start.py
node --check frontend/app.js
```

4. 提交 Pull Request，并说明改动动机、主要实现和验证方式。

## 代码风格

- 后端优先保持简单直接，后续逐步从 `main.py` 拆分模块。
- 前端不需要构建步骤，保持 `frontend/` 可直接静态托管。
- 新增实验策略或调度算法时，请附带输入、输出和边界条件说明。

## 问题反馈

提交 Issue 时请尽量包含：

- 运行环境和 Python 版本。
- 复现步骤。
- 期望行为和实际行为。
- 相关日志或截图。
