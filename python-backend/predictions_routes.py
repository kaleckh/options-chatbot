from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter

from backend_route_context import BackendRouteContext


def create_predictions_router(ctx: BackendRouteContext) -> APIRouter:
    router = APIRouter()

    @router.get("/api/predictions")
    async def get_predictions():
        """Return all predictions."""
        return ctx._load_predictions()

    @router.post("/api/predictions/grade")
    async def grade_predictions(body: dict[str, Any] | None = None):
        """Grade predictions."""
        body = body or {}
        scan_date = body.get("scan_date")
        kwargs = {}
        if scan_date:
            kwargs["scan_date"] = scan_date
        result = ctx.log_prediction(action="grade", **kwargs)
        return json.loads(result)

    @router.delete("/api/predictions/{pred_id}")
    async def delete_prediction(pred_id: int):
        """Delete a prediction by ID."""
        result = ctx.log_prediction(action="delete", prediction_id=pred_id)
        return json.loads(result)

    return router
