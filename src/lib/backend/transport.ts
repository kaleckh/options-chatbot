const PYTHON_BACKEND_URL = (
  process.env.PYTHON_BACKEND_URL || "http://localhost:8100"
).trim().replace(/\/+$/, "");
function parseBackendTimeoutMs(value: string | undefined): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 30000;
}

const PYTHON_BACKEND_TIMEOUT_MS = parseBackendTimeoutMs(
  process.env.PYTHON_BACKEND_TIMEOUT_MS
);
const JSON_REQUEST_HEADERS = { "Content-Type": "application/json" };
export const PYTHON_BACKEND_DURATION_HEADER = "x-python-backend-duration-ms";

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

async function parseBackendJsonResponse<T = Record<string, unknown>>(
  res: Response,
  errorPrefix: string
): Promise<T> {
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
      backendErrorMessage(payload, `${errorPrefix}: ${res.status}`),
      res.status,
      payload
    );
  }
  return data as T;
}

export async function fetchBackendJson<T = Record<string, unknown>>(
  path: string,
  init?: RequestInit,
  errorPrefix: string = "Python backend error"
): Promise<T> {
  const res = await fetchBackendResponse(path, init);
  return parseBackendJsonResponse<T>(res, errorPrefix);
}

export async function fetchBackendJsonWithHeaders<T = Record<string, unknown>>(
  path: string,
  init?: RequestInit,
  errorPrefix: string = "Python backend error"
): Promise<{ body: T; headers: Headers }> {
  const res = await fetchBackendResponse(path, init);
  const body = await parseBackendJsonResponse<T>(res, errorPrefix);
  return { body, headers: res.headers };
}

export function pythonBackendTimingHeaders(headers: Headers): Record<string, string> {
  const duration = headers.get(PYTHON_BACKEND_DURATION_HEADER);
  return duration ? { [PYTHON_BACKEND_DURATION_HEADER]: duration } : {};
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

function backendErrorMessage(
  payload: Record<string, unknown>,
  fallback: string
): string {
  const raw = payload.error || payload.detail || payload.message;
  if (typeof raw === "string") return raw;
  if (Array.isArray(raw)) {
    const messages = raw
      .map((item) => {
        if (!item || typeof item !== "object") return String(item);
        const record = item as Record<string, unknown>;
        const location = Array.isArray(record.loc)
          ? record.loc.join(".")
          : String(record.loc || "").trim();
        const message = String(record.msg || record.message || "").trim();
        return [location, message].filter(Boolean).join(": ");
      })
      .filter(Boolean);
    if (messages.length) return messages.join("; ");
  }
  if (raw && typeof raw === "object") {
    const record = raw as Record<string, unknown>;
    const message = record.message || record.msg || record.error;
    if (typeof message === "string" && message.trim()) {
      return message;
    }
    try {
      return JSON.stringify(raw);
    } catch {
      return fallback;
    }
  }
  return fallback;
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
): Promise<unknown> {
  const data = await fetchBackendJson<{ result?: unknown }>(
    `/api/tools/${encodeURIComponent(toolName)}`,
    {
      method: "POST",
      headers: JSON_REQUEST_HEADERS,
      body: toJsonBody(args),
    },
    "Tool call failed"
  );
  return data.result;
}
