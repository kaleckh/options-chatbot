from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any


class BackendRouteContext:
    """Late-bound access to the loaded backend module namespace.

    Test fixtures import ``main.py`` under synthetic module names and patch globals
    after app creation. Routers use this context so request handlers see those
    current module globals instead of values captured during router registration.
    """

    def __init__(self, namespace: MutableMapping[str, Any]):
        self._namespace = namespace

    def __getattr__(self, name: str) -> Any:
        try:
            return self._namespace[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def get(self, name: str, default: Any = None) -> Any:
        return self._namespace.get(name, default)
