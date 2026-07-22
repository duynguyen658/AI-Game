export type UpstreamIdentity =
  | { mode: "demo"; actorId: string; role: string }
  | { mode: "oidc"; accessToken: string };

const allowedRequestHeaders = [
  "accept",
  "content-type",
  "if-match",
  "idempotency-key",
  "x-idempotency-key",
];

export function buildUpstreamHeaders(
  browserHeaders: Headers,
  correlationId: string,
  identity: UpstreamIdentity,
) {
  const headers = new Headers();
  for (const name of allowedRequestHeaders) {
    const value = browserHeaders.get(name);
    if (value) headers.set(name, value);
  }
  headers.set("x-correlation-id", correlationId);
  if (identity.mode === "demo") {
    headers.set("x-actor-id", identity.actorId);
    headers.set("x-actor-role", identity.role);
  } else {
    headers.set("authorization", `Bearer ${identity.accessToken}`);
  }
  return headers;
}
