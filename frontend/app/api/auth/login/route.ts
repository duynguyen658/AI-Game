import { NextResponse } from "next/server";
import { getAuthAdapter } from "@/lib/auth/adapter";
import { getAuthMode } from "@/lib/env/server";

export async function GET(request: Request) {
  if (getAuthMode() !== "oidc") {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.redirect(await getAuthAdapter().createLoginRequest());
}
