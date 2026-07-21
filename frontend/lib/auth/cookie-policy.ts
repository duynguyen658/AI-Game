import type { AuthMode } from "@/lib/env/server";

export function shouldUseSecureCookies(
  nodeEnv: string | undefined,
  authMode: AuthMode,
  allowProductionDemo: boolean,
) {
  return nodeEnv === "production" && !(authMode === "demo" && allowProductionDemo);
}
