export type OidcEvent =
  | "oidc_login_started"
  | "oidc_login_completed"
  | "oidc_login_failed"
  | "oidc_access_token_refreshed"
  | "oidc_refresh_failed"
  | "oidc_session_expired"
  | "oidc_session_revoked"
  | "oidc_session_size_rejected"
  | "oidc_refresh_version_conflict";

const counters = new Map<string, number>();

const metricByEvent: Partial<Record<OidcEvent, string>> = {
  oidc_access_token_refreshed: "oidc_refresh_total",
  oidc_refresh_failed: "oidc_refresh_failures_total",
  oidc_session_expired: "oidc_session_expirations_total",
  oidc_session_revoked: "oidc_session_revocations_total",
  oidc_session_size_rejected: "oidc_cookie_size_rejections_total",
  oidc_refresh_version_conflict: "oidc_refresh_conflicts_total",
};

export function recordOidcEvent(
  event: OidcEvent,
  details: { errorCode?: string; correlationId?: string; storage?: "cookie" | "postgres" } = {},
) {
  const metric = metricByEvent[event];
  if (metric) counters.set(metric, (counters.get(metric) ?? 0) + 1);
  console.info(JSON.stringify({ event, ...details }));
}

export function oidcMetricValue(name: string) {
  return counters.get(name) ?? 0;
}
