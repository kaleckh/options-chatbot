import { NextRequest, NextResponse } from "next/server";
import { jsonError, jsonWithRouteLifecycle, readJsonObject } from "@/app/api/_utils";
import {
  createLocalOperatorSessionCookieValue,
  isLocalOperatorAuthorized,
  isLocalOperatorToken,
  LOCAL_OPERATOR_SESSION_COOKIE,
  LOCAL_OPERATOR_SESSION_MAX_AGE_SECONDS,
  LOCAL_OPERATOR_TOKEN_ENV,
  localOperatorAuthConfigured,
} from "@/lib/operator-auth";

export async function GET(req: NextRequest) {
  return jsonWithRouteLifecycle({
    configured: localOperatorAuthConfigured(),
    authorized: isLocalOperatorAuthorized(req),
  }, "operator_session_status");
}

export async function POST(req: NextRequest) {
  try {
    if (!localOperatorAuthConfigured()) {
      return NextResponse.json(
        { error: `${LOCAL_OPERATOR_TOKEN_ENV} must be configured before operator sessions can be opened.` },
        { status: 401 }
      );
    }
    const body = await readJsonObject(req);
    const token = String(body?.token || "").trim();
    if (!token || !isLocalOperatorToken(token)) {
      return NextResponse.json({ error: "Invalid local operator token." }, { status: 401 });
    }

    const response = jsonWithRouteLifecycle({ ok: true }, "operator_session_unlock");
    response.cookies.set({
      name: LOCAL_OPERATOR_SESSION_COOKIE,
      value: createLocalOperatorSessionCookieValue(),
      httpOnly: true,
      sameSite: "strict",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: LOCAL_OPERATOR_SESSION_MAX_AGE_SECONDS,
    });
    return response;
  } catch (err) {
    return jsonError(err, "Failed to open local operator session");
  }
}
