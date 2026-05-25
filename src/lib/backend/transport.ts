const PYTHON_BACKEND_URL =
  process.env.PYTHON_BACKEND_URL || "http://localhost:8100";
function parseBackendTimeoutMs(value: string | undefined): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 30000;
}

const PYTHON_BACKEND_TIMEOUT_MS = parseBackendTimeoutMs(
  process.env.PYTHON_BACKEND_TIMEOUT_MS
);
const JSON_REQUEST_HEADERS = { "Content-Type": "application/json" };

export class BackendHttpError extends Error {
  status: number;
  payload?: Record<string, unknown>;

  constructor(message: string, status: number, payload?: Record<string, unknown>) {
    super(message);
    this.name = "BackendHttpError";
    this.status = status;
    this.payload = payload;
  }
}

function buildBackendTimeoutError(path: string): Error {
  return new Error(
    `Python backend request timed out for ${path} after ${Math.round(PYTHON_BACKEND_TIMEOUT_MS / 1000)}s`
  );
}

export async function fetchBackendResponse(
  path: string,
  init?: RequestInit
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), PYTHON_BACKEND_TIMEOUT_MS);
  try {
    return await fetch(`${PYTHON_BACKEND_URL}${path}`, {
      ...init,
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw buildBackendTimeoutError(path);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function fetchBackendJson<T = Record<string, unknown>>(
  path: string,
  init?: RequestInit,
  errorPrefix: string = "Python backend error"
): Promise<T> {
  const res = await fetchBackendResponse(path, init);
  const text = await res.text();
  let data: unknown = {};
  if (text.trim()) {
    try {
      data = JSON.parse(text);
    } catch {
      if (res.ok) {
        throw new BackendHttpError(
          `${errorPrefix}: invalid JSON response`,
          502,
          { message: text.slice(0, 500) }
        );
      }
      data = { message: text };
    }
  }
  if (!res.ok) {
    const payload = data as Record<string, unknown>;
    throw new BackendHttpError(
      String(payload.error || payload.detail || payload.message || `${errorPrefix}: ${res.status}`),
      res.status,
      payload
    );
  }
  return data as T;
}

export function toJsonBody(value: Record<string, unknown>): string {
  return JSON.stringify(value);
}

export function toSearchSuffix(params: Record<string, unknown> = {}): string {
  const search = new URLSearchParams(
    Object.entries(params).reduce<Record<string, string>>((acc, [key, value]) => {
      if (value != null) acc[key] = String(value);
      return acc;
    }, {})
  );
  return search.toString() ? `?${search.toString()}` : "";
}

function normalizeToolResult(result: unknown): string {
  if (result == null) return "";
  if (typeof result === "string") return result;
  return JSON.stringify(result) ?? "";
}

export async function postBackendJson<T = Record<string, unknown>>(
  path: string,
  payload: Record<string, unknown>,
  errorPrefix: string
): Promise<T> {
  return fetchBackendJson<T>(
    path,
    {
      method: "POST",
      headers: JSON_REQUEST_HEADERS,
      body: toJsonBody(payload),
    },
    errorPrefix
  );
}

export async function putBackendJson(
  path: string,
  payload: Record<string, unknown>,
  errorPrefix: string
): Promise<void> {
  await fetchBackendJson<Record<string, unknown>>(
    path,
    {
      method: "PUT",
      headers: JSON_REQUEST_HEADERS,
      body: toJsonBody(payload),
    },
    errorPrefix
  );
}

export async function callTool(
  toolName: string,
  args: Record<string, unknown>
): Promise<string> {
  const data = await fetchBackendJson<{ result?: unknown }>(
    `/api/tools/${encodeURIComponent(toolName)}`,
    {
      method: "POST",
      headers: JSON_REQUEST_HEADERS,
      body: toJsonBody(args),
    },
    "Tool call failed"
  );
  return normalizeToolResult(data.result);
}
