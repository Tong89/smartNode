# -*- coding: utf-8 -*-
"""契约测试：OpenAPI 规范声明的 path/method 必须存在于实际路由，守护一致性。"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.openapi import OPENAPI_SPEC  # noqa: E402


def _real_routes(app):
    routes = {}
    for rule in app.url_map.iter_rules():
        methods = {m for m in rule.methods if m in {"GET", "POST", "PUT", "DELETE", "PATCH"}}
        routes.setdefault(str(rule.rule), set()).update(methods)
    return routes


def test_documented_paths_exist():
    import backend.api as api
    api.simulation_engine.running = False
    routes = _real_routes(api.app)
    missing = []
    for path, methods in OPENAPI_SPEC["paths"].items():
        if path not in routes:
            missing.append(path)
            continue
        for method in methods:
            if method.upper() not in routes[path]:
                missing.append(f"{method.upper()} {path}")
    assert not missing, f"OpenAPI 声明但路由缺失: {missing}"


def test_spec_is_openapi_31():
    assert OPENAPI_SPEC["openapi"].startswith("3.1")
    assert OPENAPI_SPEC["info"]["version"]
