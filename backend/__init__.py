"""SmartNode backend package.

惰性暴露 app/run/simulation_engine：仅在显式访问时才导入 backend.api（从而创建引擎并启动线程），
使 ``import backend.core`` 等不再因包初始化而产生副作用。
"""

__all__ = ["app", "run", "simulation_engine"]


def __getattr__(name):
    if name in __all__:
        from backend import api
        return getattr(api, name)
    raise AttributeError(f"module 'backend' has no attribute {name!r}")
