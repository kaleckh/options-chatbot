"""Command-line entrypoint for ``python -m scripts.agent_control``."""

from .legacy import main


if __name__ == "__main__":
    raise SystemExit(main())
