"""Agent-control package compatibility exports."""

import sys
import types

from . import legacy as _legacy


class _AgentControlModule(types.ModuleType):
    def __getattr__(self, name: str):
        return getattr(_legacy, name)

    def __setattr__(self, name: str, value):
        if not name.startswith("__"):
            setattr(_legacy, name, value)
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _AgentControlModule
globals().update({name: value for name, value in vars(_legacy).items() if not name.startswith("__")})
__all__ = [name for name in globals() if not name.startswith("__")]
