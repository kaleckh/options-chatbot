import { createHmac, timingSafeEqual } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

export const LOCAL_OPERATOR_TOKEN_ENV = "OPTIONS_LOCAL_OPERATOR_TOKEN";
export const LEGACY_OPERATOR_TOKEN_ENV = "OPTIONS_OPERATOR_TOKEN";
export const LOCAL_OPERATOR_SESSION_SECRET_ENV = "OPTIONS_LOCAL_OPERATOR_SESSION_SECRET";
export const LOCAL_OPERATOR_TOKEN_HEADER = "x-options-operator-token";
export const LOCAL_OPERATOR_SESSION_COOKIE = "options_local_operator_session";
export const LOCAL_OPERATOR_SESSION_MAX_AGE_SECONDS = 8 * 60 * 60;

type RuntimeEnv = Record<string, string | undefined>;

function runtimeEnv(): RuntimeEnv {
  return typeof process === "undefined" ? {} : process.env;
}

export function localOperatorTokenFromEnv(env: RuntimeEnv = runtimeEnv()): string {
  return String(env[LOCAL_OPERATOR_TOKEN_ENV] || env[LEGACY_OPERATOR_TOKEN_ENV] || "").trim();
}

function localOperatorSessionSecret(env: RuntimeEnv = runtimeEnv()): string {
  return String(env[LOCAL_OPERATOR_SESSION_SECRET_ENV] || localOperatorTokenFromEnv(env)).trim();
}

export function localOperatorAuthConfigured(env: RuntimeEnv = runtimeEnv()): boolean {
  return Boolean(localOperatorTokenFromEnv(env));
}

function constantTimeEqual(actual: string, expected: string): boolean {
  if (!actual || !expected) return false;
  const actualBytes = Buffer.from(actual);
  const expectedBytes = Buffer.from(expected);
  if (actualBytes.length !== expectedBytes.length) return false;
  return timingSafeEqual(actualBytes, expectedBytes);
}

export function isLocalOperatorToken(
  candidate: string,
  env: RuntimeEnv = runtimeEnv()
): boolean {
  return constantTimeEqual(String(candidate || "").trim(), localOperatorTokenFromEnv(env));
}

function bearerToken(authorizationHeader: string | null): string {
  const match = String(authorizationHeader || "").match(/^Bearer\s+(.+)$/i);
  return match ? match[1].trim() : "";
}

function requestOperatorToken(req: NextRequest): string {
  return (
    String(req.headers.get(LOCAL_OPERATOR_TOKEN_HEADER) || "").trim() ||
    bearerToken(req.headers.get("authorization"))
  );
}

function sessionSignature(payload: string, env: RuntimeEnv = runtimeEnv()): string {
  const secret = localOperatorSessionSecret(env);
  if (!secret) return "";
  return createHmac("sha256", secret).update(payload).digest("base64url");
}

export function createLocalOperatorSessionCookieValue(
  issuedAtSeconds: number = Math.floor(Date.now() / 1000),
  env: RuntimeEnv = runtimeEnv()
): string {
  const payload = `v1.${issuedAtSeconds}`;
  return `${payload}.${sessionSignature(payload, env)}`;
}

function requestCookieValue(req: NextRequest, name: string): string {
  const cookie = req.cookies?.get(name);
  if (typeof cookie === "string") return cookie;
  return String(cookie?.value || "");
}

function isValidLocalOperatorSession(
  cookieValue: string,
  env: RuntimeEnv = runtimeEnv(),
  nowSeconds: number = Math.floor(Date.now() / 1000)
): boolean {
  const parts = String(cookieValue || "").split(".");
  if (parts.length !== 3 || parts[0] !== "v1") return false;
  const issuedAtSeconds = Number(parts[1]);
  if (!Number.isFinite(issuedAtSeconds)) return false;
  if (issuedAtSeconds > nowSeconds) return false;
  if (nowSeconds - issuedAtSeconds > LOCAL_OPERATOR_SESSION_MAX_AGE_SECONDS) {
    return false;
  }
  const payload = `${parts[0]}.${parts[1]}`;
  return constantTimeEqual(parts[2], sessionSignature(payload, env));
}

export function isLocalOperatorAuthorized(
  req: NextRequest,
  env: RuntimeEnv = runtimeEnv()
): boolean {
  if (!localOperatorAuthConfigured(env)) return false;
  const token = requestOperatorToken(req);
  if (token && isLocalOperatorToken(token, env)) return true;
  return isValidLocalOperatorSession(requestCookieValue(req, LOCAL_OPERATOR_SESSION_COOKIE), env);
}

export function requireLocalOperator(req: NextRequest) {
  if (!localOperatorAuthConfigured()) {
    return NextResponse.json(
      {
        error: `${LOCAL_OPERATOR_TOKEN_ENV} must be configured before calling state-changing routes.`,
      },
      { status: 401 }
    );
  }
  if (isLocalOperatorAuthorized(req)) return null;
  return NextResponse.json(
    {
      error: `Local operator authorization requires ${LOCAL_OPERATOR_TOKEN_HEADER}, an Authorization bearer token, or an operator session cookie.`,
    },
    { status: 401 }
  );
}
