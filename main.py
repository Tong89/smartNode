# -*- coding: utf-8 -*-
"""Compatibility entrypoint for SmartNode.

Backend code now lives in ``backend.core`` and ``backend.api``. Keep this file
so older launch scripts that import ``main`` continue to work.
"""

from backend.api import app, run, simulation_engine


if __name__ == '__main__':
    print('=' * 60)
    print('天基智枢 SmartNode 仿真平台启动中...')
    print('访问地址: http://127.0.0.1:5000/frontend/')
    print('=' * 60)
    run()
