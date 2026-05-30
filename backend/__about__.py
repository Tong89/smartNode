# -*- coding: utf-8 -*-
"""SmartNode version single source of truth.

All other modules should import __version__ from here rather than
hard-coding a version string.  The pyproject.toml [project] version is
kept in sync manually.

Usage::

    from backend.__about__ import __version__
"""

__all__ = [
    "__title__",
    "__description__",
    "__version__",
    "__author__",
    "__license__",
]

__title__: str = "smartnode"
__description__: str = "天基智枢 SmartNode 卫星中继仿真平台"
__version__: str = "1.1.0"
__author__: str = "Tong89"
__license__: str = "MIT"
