import { NextResponse } from "next/server";
import { getAuthAdapter } from "@/lib/auth/adapter";
import { getAuthMode, requireServerEnv } from "@/lib/env/server";
import { recordOidcEvent } from "@/lib/auth/observability";

export async function GET(request: Request) {
  if (getAuthMode() !== "oidc") {
    return NextResponse.json({ message: "OIDC authentication is disabled" }, { status: 404 });
  }
  try {
    await getAuthAdapter().handleCallback(request);
    return NextResponse.redirect(new URL("/dashboard", requireServerEnv("OIDC_REDIRECT_URI")));
  } catch (error) {
    const candidate = error && typeof error === "object" ? error as Record<string, unknown> : {};
    const safeCode = typeof candidate.code === "string" && /^[A-Z0-9_]{1,64}$/.test(candidate.code)
      ? candidate.code
      : "OIDC_CALLBACK_FAILED";
    recordOidcEvent("oidc_login_failed", { errorCode: safeCode });
    return NextResponse.redirect(new URL("/login?error=oidc", requireServerEnv("OIDC_REDIRECT_URI")));
  }
}
