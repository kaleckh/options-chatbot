import { fetchBackendJson } from "@/lib/backend/transport";

export async function getSectorSentiments(): Promise<unknown[]> {
  return fetchBackendJson<unknown[]>(
    "/api/sectors",
    undefined,
    "Failed to fetch sector data"
  );
}
