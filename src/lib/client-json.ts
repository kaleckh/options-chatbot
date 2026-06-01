function buildTimeoutError(label: string, timeoutMs: number): Error {
  return new Error(`${label} timed out after ${Math.round(timeoutMs / 1000)}s.`);
}

function payloadErrorMessage(payload: unknown): string | null {
  if (
    payload &&
    typeof payload === "object" &&
    !Array.isArray(payload) &&
    "error" in payload
  ) {
    return String((payload as { error?: unknown }).error || "Request failed.");
  }
  return null;
}

function responsePreview(text: string): string {
  return text.replace(/\s+/g, " ").trim().slice(0, 160);
}

async function parseJsonResponse(res: Response, label: string): Promise<unknown> {
  const text = await res.text();
  if (!text.trim()) return {};
  try {
    return JSON.parse(text) as unknown;
  } catch {
    const contentType = res.headers.get("content-type") || "unknown content type";
    const preview = responsePreview(text);
    const detail = contentType.includes("text/html")
      ? "received HTML instead of JSON"
      : `received non-JSON response (${contentType})`;
    throw new Error(
      `${label} ${detail} with status ${res.status}${preview ? `: ${preview}` : ""}`
    );
  }
}

export async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit | undefined,
  label: string,
  timeoutMs: number = 30000
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw buildTimeoutError(label, timeoutMs);
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export async function readJsonResponseOrThrow<T = unknown>(
  res: Response,
  label: string
): Promise<T> {
  const data = await parseJsonResponse(res, label);
  const errorMessage = payloadErrorMessage(data);
  if (!res.ok || errorMessage) {
    throw new Error(errorMessage || `${label} request failed with status ${res.status}`);
  }
  return data as T;
}
