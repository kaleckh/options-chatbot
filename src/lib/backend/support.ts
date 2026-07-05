import { fetchBackendJson } from "@/lib/backend/transport";

export async function getSectorSentiments(): Promise<unknown[]> {
  return fetchBackendJson<unknown[]>(
    "/api/sectors",
    undefined,
    "Failed to fetch sector data"
  );
}

export async function getCurrentPolicyHistoricalPicks(): Promise<Record<string, unknown>> {
  return fetchBackendJson<Record<string, unknown>>(
    "/api/current-policy-historical-picks",
    undefined,
    "Failed to fetch current-policy historical picks"
  );
}
