import { NextResponse } from "next/server";
import { getAuthAdapter } from "@/lib/auth/adapter";
import { getAuthMode } from "@/lib/env/server";

export async function GET(request: Request) {
  if (getAuthMode() !== "oidc") {
    return NextResponse.json({ message: "OIDC authentication is disabled" }, { status: 404 });
  }
  try {
    await getAuthAdapter().handleCallback(request);
    return NextResponse.redirect(new URL("/dashboard", request.url));
  } catch {
    return NextResponse.redirect(new URL("/login?error=oidc", request.url));
  }
}
