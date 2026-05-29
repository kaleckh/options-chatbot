import { fetchBackendJson, putBackendJson, toSearchSuffix } from "@/lib/backend/transport";

export async function getRiskSettings(): Promise<Record<string, unknown>> {
  return fetchBackendJson<Record<string, unknown>>("/api/risk");
}

export async function getChangelog(profile: string = "equity"): Promise<unknown[]> {
  return fetchBackendJson<unknown[]>(`/api/changelog?profile=${encodeURIComponent(profile)}`);
}

export async function getProfile(
  profileType: "equity" | "index" = "equity"
): Promise<Record<string, unknown>> {
  return fetchBackendJson<Record<string, unknown>>(
    `/api/profile${toSearchSuffix({ type: profileType })}`,
    undefined,
    "Failed to fetch profile"
  );
}

export async function saveProfile(
  profileType: string,
  updates: Record<string, unknown>,
  note?: string
): Promise<void> {
  await putBackendJson(
    "/api/profile",
    { type: profileType, updates, note },
    "Failed to save profile"
  );
}
