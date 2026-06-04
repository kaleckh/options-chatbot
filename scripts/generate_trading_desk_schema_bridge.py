from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PYTHON_MODELS_PATH = ROOT / "python-backend" / "trading_desk_api_models.py"
TS_API_CONTRACTS_PATH = ROOT / "src" / "lib" / "trading-desk" / "apiContracts.ts"
STORE_OWNERSHIP_PATH = ROOT / "src" / "lib" / "trading-desk" / "storeOwnership.ts"
JSON_OUTPUT_PATH = ROOT / "data" / "contracts" / "trading-desk-api-schema-bridge.json"
MD_OUTPUT_PATH = ROOT / "docs" / "trading-desk-schema-bridge.md"

PYDANTIC_SCHEMA_MODELS = (
    "CreateTradingDeskRecordBody",
    "ReviewTradingDeskRecordsBody",
    "CloseTradingDeskRecordBody",
    "TrackedPositionEnvelope",
    "TrackedPositionsEnvelope",
    "SuggestedTradeEnvelope",
    "SuggestedTradesEnvelope",
)

NON_GOALS = (
    "No FastAPI response_model decorators or endpoint body annotations.",
    "No automatic FastAPI 422 request validation.",
    "No OpenAPI generation, serving, or replacement for FastAPI route metadata.",
    "No runtime JSON Schema, Zod, or AJV validation.",
    "No generated TypeScript replacement for the manual Trading Desk contracts.",
    "No response payload reshaping, auth/header/cookie behavior changes, or DB changes.",
    "No deep TrackedPosition, SuggestedTrade, ScanPick, proof, scanner, replay, P&L, or review schemas.",
    "No Strategy Lab, generic route lifecycle, backend-only FastAPI, AI commodity, crypto, Polymarket, or day-trading schema sweep.",
)


def _load_python_models_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("trading_desk_api_models_bridge", PYTHON_MODELS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {PYTHON_MODELS_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _string_field(body: str, name: str) -> str:
    match = re.search(rf"\b{name}:\s*\"([^\"]*)\"", body)
    return match.group(1) if match else ""


def _extract_store_contracts() -> dict[str, dict[str, str]]:
    source = _read(STORE_OWNERSHIP_PATH)
    contracts: dict[str, dict[str, str]] = {}
    pattern = re.compile(r"^\s{2}([A-Za-z0-9_]+):\s*\{(.*?)^\s{2}\},", re.MULTILINE | re.DOTALL)
    for match in pattern.finditer(source):
        route_id = match.group(1)
        body = match.group(2)
        contracts[route_id] = {
            "id": _string_field(body, "id") or route_id,
            "method": _string_field(body, "method"),
            "route": _string_field(body, "route"),
            "store": _string_field(body, "store"),
            "lifecycle": _string_field(body, "lifecycle"),
            "record_class": _string_field(body, "recordClass"),
            "owner": _string_field(body, "owner"),
        }
    return contracts


def _extract_ts_api_contracts() -> dict[str, dict[str, Any]]:
    source = _read(TS_API_CONTRACTS_PATH)
    array_match = re.search(
        r"export const TRADING_DESK_API_CONTRACTS:[\s\S]*?=\s*\[(?P<body>[\s\S]*?)\];",
        source,
    )
    if not array_match:
        raise RuntimeError(f"Unable to find TRADING_DESK_API_CONTRACTS in {TS_API_CONTRACTS_PATH}")
    contracts: dict[str, dict[str, Any]] = {}
    object_pattern = re.compile(
        r"\{\s*"
        r"id:\s*\"(?P<id>[^\"]+)\",\s*"
        r"request:\s*(?P<request>null|\"[^\"]+\"),\s*"
        r"response:\s*\"(?P<response>[^\"]+)\",\s*"
        r"envelope:\s*\"(?P<envelope>[^\"]+)\",\s*"
        r"includesPositionEventPersistence:\s*(?P<event>true|false),\s*"
        r"\}",
        re.DOTALL,
    )
    for match in object_pattern.finditer(array_match.group("body")):
        request = match.group("request")
        contracts[match.group("id")] = {
            "request": None if request == "null" else request.strip('"'),
            "response": match.group("response"),
            "envelope": match.group("envelope"),
            "includes_position_event_persistence": match.group("event") == "true",
        }
    if not contracts:
        raise RuntimeError(f"Unable to parse Trading Desk API contracts from {TS_API_CONTRACTS_PATH}")
    return contracts


def _pydantic_model_schemas(module: ModuleType) -> dict[str, dict[str, Any]]:
    schemas: dict[str, dict[str, Any]] = {}
    for model_name in PYDANTIC_SCHEMA_MODELS:
        model_type = getattr(module, model_name)
        schemas[model_name] = model_type.model_json_schema(ref_template="#/$defs/{model}")
    return schemas


def _validate_sources(
    store_contracts: dict[str, dict[str, str]],
    ts_contracts: dict[str, dict[str, Any]],
    pydantic_manifest: dict[str, dict[str, str]],
) -> None:
    store_ids = set(store_contracts)
    ts_ids = set(ts_contracts)
    pydantic_ids = set(pydantic_manifest)
    if store_ids != ts_ids:
        raise RuntimeError(
            "Trading Desk store and TypeScript contract ids differ: "
            f"store_only={sorted(store_ids - ts_ids)} ts_only={sorted(ts_ids - store_ids)}"
        )
    expected_mutation_ids = {route_id for route_id, contract in store_contracts.items() if contract["method"] != "GET"}
    if pydantic_ids != expected_mutation_ids:
        raise RuntimeError(
            "Pydantic model manifest must cover exactly Trading Desk mutation routes: "
            f"missing={sorted(expected_mutation_ids - pydantic_ids)} extra={sorted(pydantic_ids - expected_mutation_ids)}"
        )


def build_schema_bridge() -> dict[str, Any]:
    module = _load_python_models_module()
    store_contracts = _extract_store_contracts()
    ts_contracts = _extract_ts_api_contracts()
    pydantic_manifest = {
        route["route_id"]: route
        for route in module.trading_desk_api_model_manifest()
    }
    _validate_sources(store_contracts, ts_contracts, pydantic_manifest)

    route_contracts: list[dict[str, Any]] = []
    for route_id in sorted(store_contracts, key=lambda value: (store_contracts[value]["route"], store_contracts[value]["method"])):
        store_contract = store_contracts[route_id]
        ts_contract = ts_contracts[route_id]
        pydantic_contract = pydantic_manifest.get(route_id)
        entry: dict[str, Any] = {
            "route_id": route_id,
            "family": "trading_desk",
            "method": store_contract["method"],
            "route": store_contract["route"],
            "store": store_contract["store"],
            "lifecycle": store_contract["lifecycle"],
            "record_class": store_contract["record_class"],
            "owner": store_contract["owner"],
            "runtime_use": False,
            "typescript": ts_contract,
        }
        if pydantic_contract:
            entry["schema_status"] = "pydantic_adapter_schema"
            entry["pydantic"] = {
                "request_model": pydantic_contract["request_model"],
                "response_envelope_model": pydantic_contract["response_envelope_model"],
                "request_schema_ref": f"#/$defs/{pydantic_contract['request_model']}",
                "response_envelope_schema_ref": f"#/$defs/{pydantic_contract['response_envelope_model']}",
                "notes": pydantic_contract["notes"],
            }
        else:
            entry["schema_status"] = "typescript_contract_only"
            entry["pydantic"] = None
        route_contracts.append(entry)

    return {
        "schema_version": 1,
        "artifact": "trading_desk_api_schema_bridge",
        "generated_by": "scripts/generate_trading_desk_schema_bridge.py",
        "runtime_use": False,
        "scope": "Generated documentation and drift-check bridge for the active Trading Desk API contract slice.",
        "sources": [
            "python-backend/trading_desk_api_models.py",
            "src/lib/trading-desk/apiContracts.ts",
            "src/lib/trading-desk/storeOwnership.ts",
        ],
        "non_goals": list(NON_GOALS),
        "route_contracts": route_contracts,
        "json_schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$defs": _pydantic_model_schemas(module),
        },
    }


def render_json(bridge: dict[str, Any]) -> str:
    return json.dumps(bridge, indent=2, sort_keys=True) + "\n"


def _md_cell(value: Any) -> str:
    if value is None:
        return "none"
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_markdown(bridge: dict[str, Any]) -> str:
    lines = [
        "# Trading Desk Schema Bridge",
        "",
        "Generated by `scripts/generate_trading_desk_schema_bridge.py`. Do not hand-edit this file.",
        "",
        "This bridge is documentation and drift-check metadata only. `runtime_use` is `false`: it is not FastAPI `response_model`, automatic `422` validation, Zod/AJV validation, generated TypeScript, or public payload reshaping.",
        "",
        "## Sources",
        "",
    ]
    lines.extend(f"- `{source}`" for source in bridge["sources"])
    lines.extend(
        [
            "",
            "## Route Contract Bridge",
            "",
            "| Contract | Route | Store | Lifecycle | TS request | TS response | Pydantic request | Pydantic response envelope | Status |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for contract in bridge["route_contracts"]:
        pydantic = contract.get("pydantic") or {}
        typescript = contract["typescript"]
        lines.append(
            "| "
            + " | ".join(
                [
                    _md_cell(contract["route_id"]),
                    _md_cell(f"{contract['method']} {contract['route']}"),
                    _md_cell(contract["store"]),
                    _md_cell(contract["lifecycle"]),
                    _md_cell(typescript.get("request")),
                    _md_cell(typescript.get("response")),
                    _md_cell(pydantic.get("request_model")),
                    _md_cell(pydantic.get("response_envelope_model")),
                    _md_cell(contract["schema_status"]),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## JSON Schema Definitions",
            "",
            "The generated JSON artifact stores Pydantic adapter schemas under `json_schema.$defs`. Those schemas describe only the intentionally loose request-body adapters and top-level response envelopes from `python-backend/trading_desk_api_models.py`.",
            "",
            "They do not describe deep `TrackedPosition`, `SuggestedTrade`, `ScanPick`, proof, scanner-lineage, quote, P&L, latest-review, replay, profile, or tool payloads.",
            "",
            "## Non-Goals",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in bridge["non_goals"])
    lines.append("")
    return "\n".join(lines)


def _check_file(path: Path, expected: str) -> str | None:
    if not path.exists():
        return f"Missing generated artifact: {path.relative_to(ROOT).as_posix()}"
    actual = path.read_text(encoding="utf-8")
    if actual != expected:
        return f"Generated artifact is stale: {path.relative_to(ROOT).as_posix()}"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the Trading Desk API schema bridge.")
    parser.add_argument("--check", action="store_true", help="Fail if generated artifacts are stale.")
    args = parser.parse_args(argv)

    bridge = build_schema_bridge()
    json_text = render_json(bridge)
    markdown_text = render_markdown(bridge)

    if args.check:
        errors = [
            error
            for error in (
                _check_file(JSON_OUTPUT_PATH, json_text),
                _check_file(MD_OUTPUT_PATH, markdown_text),
            )
            if error
        ]
        if errors:
            for error in errors:
                print(error, file=sys.stderr)
            return 1
        return 0

    JSON_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    MD_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUTPUT_PATH.write_text(json_text, encoding="utf-8")
    MD_OUTPUT_PATH.write_text(markdown_text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
