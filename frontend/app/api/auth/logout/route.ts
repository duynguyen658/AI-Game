import { NextResponse } from "next/server";
import { getAuthAdapter } from "@/lib/auth/adapter";

export async function GET(request: Request) {
  const providerLogout = await getAuthAdapter().logout();
  return NextResponse.redirect(providerLogout ?? new URL("/login", request.url));
}
