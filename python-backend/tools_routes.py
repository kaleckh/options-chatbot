from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException

from backend_route_context import BackendRouteContext


def _coerce_tool_result(result: Any) -> Any:
    if not isinstance(result, str):
        return result
    text = result.strip()
    if not text or text[0] not in "[{":
        return result
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return result


def create_tools_router(ctx: BackendRouteContext) -> APIRouter:
    router = APIRouter()

    @router.post("/api/tools/{tool_name}")
    async def call_tool_endpoint(tool_name: str, body: dict[str, Any] | None = None):
        """Execute any registered tool function by name."""
        body = body or {}
        fn = ctx.TOOL_DISPATCH.get(tool_name)
        if not fn:
            raise HTTPException(404, f"Unknown tool: {tool_name}")
        try:
            result = await ctx._run_in_worker(fn, **body)
            return {"result": _coerce_tool_result(result)}
        except Exception as e:
            raise HTTPException(500, {"error": type(e).__name__, "message": str(e)})

    return router
