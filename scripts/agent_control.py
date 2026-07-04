"""Compatibility shim for the agent-control package."""

from agent_control import legacy as _legacy

globals().update({name: value for name, value in vars(_legacy).items() if not name.startswith("__")})
main = _legacy.main


if __name__ == "__main__":
    raise SystemExit(main())
