# -*- coding: utf-8 -*-
"""Desktop-friendly launcher for the separated simulation app."""

import os
import sys
import threading
import time
import webbrowser


if sys.stdout:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

from backend.api import app  # noqa: E402


def run_server():
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False, threaded=True)


def open_window(url):
    try:
        import webview

        webview.create_window(
            "天基智枢 SmartNode 仿真平台",
            url,
            width=1440,
            height=900,
            resizable=True,
        )
        webview.start()
    except Exception:
        webbrowser.open(url)
        print(f"已在默认浏览器打开：{url}")
        while True:
            time.sleep(3600)


if __name__ == "__main__":
    url = "http://127.0.0.1:5000/frontend/"
    print("=" * 58)
    print("天基智枢 SmartNode 仿真平台")
    print("后端 API: http://127.0.0.1:5000/api/health")
    print(f"前端页面: {url}")
    print("按 Ctrl+C 停止服务")
    print("=" * 58)

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    time.sleep(1.0)
    open_window(url)
