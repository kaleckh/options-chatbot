from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.operational_provenance import current_host_name  # noqa: E402


REPORT_ID = "evidence_host_policy"
DEFAULT_POLICY_PATH = ROOT / "data" / "contracts" / "evidence-host-policy.json"


def _norm_host(value: Any) -> str:
    return str(value or "").strip().lower()


def load_evidence_host_policy(path: Path = DEFAULT_POLICY_PATH) -> dict[str, Any]:
    if not path.exists():
        return {
            "report_id": REPORT_ID,
            "available": False,
            "path": str(path),
            "authoritative_host": os.getenv("OPTIONS_AUTHORITATIVE_EVIDENCE_HOST"),
            "read_only_hosts": [],
        }
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {
            "report_id": REPORT_ID,
            "available": False,
            "path": str(path),
            "error": "json_root_not_object",
            "authoritative_host": os.getenv("OPTIONS_AUTHORITATIVE_EVIDENCE_HOST"),
            "read_only_hosts": [],
        }
    payload.setdefault("available", True)
    payload.setdefault("path", str(path))
    return payload


def evidence_host_status(
    *,
    policy_path: Path = DEFAULT_POLICY_PATH,
    current_host: str | None = None,
) -> dict[str, Any]:
    policy = load_evidence_host_policy(policy_path)
    host = current_host or current_host_name()
    env_authoritative = os.getenv("OPTIONS_AUTHORITATIVE_EVIDENCE_HOST")
    authoritative_host = str(env_authoritative or policy.get("authoritative_host") or "").strip()
    read_only_hosts = [
        str(item).strip()
        for item in list(policy.get("read_only_hosts") or [])
        if str(item or "").strip()
    ]
    normalized_host = _norm_host(host)
    normalized_authoritative = _norm_host(authoritative_host)
    normalized_read_only = {_norm_host(item) for item in read_only_hosts}

    if normalized_authoritative and normalized_host == normalized_authoritative:
        role = "authoritative"
        write_allowed = True
        status = "authoritative_host"
    elif normalized_host in normalized_read_only:
        role = "read_only_replica"
        write_allowed = False
        status = "read_only_replica"
    else:
        role = "unclassified"
        write_allowed = False
        status = "unclassified_host"

    return {
        "report_id": REPORT_ID,
        "status": status,
        "current_host": host,
        "authoritative_host": authoritative_host or None,
        "role": role,
        "write_allowed": write_allowed,
        "policy_path": str(policy_path),
        "policy_available": bool(policy.get("available")),
        "read_only_hosts": read_only_hosts,
        "source_of_truth": policy.get("source_of_truth") or {},
        "operator_rule": (
            "Only the authoritative host should append forward evidence or mutate evidence stores; "
            "replicas may run read-only reports after sync."
        ),
    }


def main() -> int:
    status = evidence_host_status()
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0 if status["write_allowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
