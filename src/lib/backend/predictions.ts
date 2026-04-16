import { fetchBackendJson, postBackendJson } from "@/lib/backend/transport";

export async function gradePredictions(
  payload: Record<string, unknown> = {}
): Promise<Record<string, unknown>> {
  return postBackendJson<Record<string, unknown>>(
    "/api/predictions/grade",
    payload,
    "Failed to grade predictions"
  );
}

export async function getPredictions(): Promise<unknown[]> {
  return fetchBackendJson<unknown[]>(
    "/api/predictions",
    undefined,
    "Failed to fetch predictions"
  );
}
