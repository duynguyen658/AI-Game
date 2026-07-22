import { createHash, generateKeyPairSync, randomBytes, sign } from "node:crypto";
import { createServer } from "node:http";

const issuer = process.env.TEST_OIDC_ISSUER ?? "http://127.0.0.1:43132";
const clientId = process.env.OIDC_CLIENT_ID ?? "cyber-legends";
const clientSecret = process.env.OIDC_CLIENT_SECRET ?? "deterministic-test-client-secret";
const accessLifetime = Number.parseInt(process.env.TEST_OIDC_ACCESS_TOKEN_SECONDS ?? "2", 10);
const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
const kid = "m8-test-key";
const jwk = publicKey.export({ format: "jwk" });
const codes = new Map();
const refreshTokens = new Map();
const counters = { authorization_count: 0, token_request_count: 0, code_exchange_count: 0, refresh_count: 0, rotation_count: 0, logout_count: 0, last_error: null };

function base64url(value) {
  return Buffer.from(typeof value === "string" ? value : JSON.stringify(value)).toString("base64url");
}

function jwt(claims) {
  const encoded = `${base64url({ alg: "RS256", kid, typ: "JWT" })}.${base64url(claims)}`;
  return `${encoded}.${sign("RSA-SHA256", Buffer.from(encoded), privateKey).toString("base64url")}`;
}

function tokenHash(value) {
  return createHash("sha256").update(value).digest().subarray(0, 16).toString("base64url");
}

function issueTokens(nonce, generation = 1) {
  const now = Math.floor(Date.now() / 1000);
  const accessToken = jwt({ iss: issuer, aud: clientId, sub: "oidc-test-user", role: "manager", name: "OIDC Test User", iat: now, exp: now + accessLifetime, generation });
  const refreshToken = randomBytes(32).toString("base64url");
  refreshTokens.set(refreshToken, { nonce, generation, active: true });
  const idToken = jwt({ iss: issuer, aud: clientId, sub: "oidc-test-user", role: "manager", name: "OIDC Test User", nonce, at_hash: tokenHash(accessToken), iat: now, exp: now + 300 });
  return { access_token: accessToken, refresh_token: refreshToken, id_token: idToken, token_type: "Bearer", expires_in: accessLifetime };
}

function json(response, status, body) {
  response.writeHead(status, { "content-type": "application/json", "cache-control": "no-store" });
  response.end(JSON.stringify(body));
}

function oauthError(response, error, description, diagnostic = error) {
  counters.last_error = diagnostic;
  json(response, 400, { error, error_description: description });
}

async function requestBody(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  return new URLSearchParams(Buffer.concat(chunks).toString("utf8"));
}

function validClient(request, body) {
  const authorization = request.headers.authorization;
  if (authorization?.startsWith("Basic ")) {
    const [id, secret] = Buffer.from(authorization.slice(6), "base64").toString("utf8").split(":");
    return id === clientId && secret === clientSecret;
  }
  return body.get("client_id") === clientId && body.get("client_secret") === clientSecret;
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", issuer);
  if (url.pathname === "/.well-known/openid-configuration") {
    return json(response, 200, {
      issuer,
      authorization_endpoint: `${issuer}/authorize`,
      token_endpoint: `${issuer}/token`,
      jwks_uri: `${issuer}/jwks`,
      end_session_endpoint: `${issuer}/logout`,
      response_types_supported: ["code"],
      subject_types_supported: ["public"],
      id_token_signing_alg_values_supported: ["RS256"],
      token_endpoint_auth_methods_supported: ["client_secret_post", "client_secret_basic"],
      code_challenge_methods_supported: ["S256"],
      scopes_supported: ["openid", "profile", "email"],
    });
  }
  if (url.pathname === "/jwks") return json(response, 200, { keys: [{ ...jwk, kid, use: "sig", alg: "RS256" }] });
  if (url.pathname === "/authorize") {
    const redirectUri = url.searchParams.get("redirect_uri");
    const state = url.searchParams.get("state");
    const nonce = url.searchParams.get("nonce");
    const challenge = url.searchParams.get("code_challenge");
    if (!redirectUri || !state || !nonce || !challenge || url.searchParams.get("code_challenge_method") !== "S256") {
      return oauthError(response, "invalid_request", "PKCE, state, and nonce are required");
    }
    const code = randomBytes(24).toString("base64url");
    codes.set(code, { redirectUri, nonce, challenge, used: false });
    counters.authorization_count += 1;
    const callback = new URL(redirectUri);
    callback.searchParams.set("code", code);
    callback.searchParams.set("state", state);
    response.writeHead(302, { location: callback.toString(), "cache-control": "no-store" });
    return response.end();
  }
  if (url.pathname === "/token" && request.method === "POST") {
    counters.token_request_count += 1;
    const body = await requestBody(request);
    if (!validClient(request, body)) return oauthError(response, "invalid_client", "Client authentication failed");
    if (body.get("grant_type") === "authorization_code") {
      const record = codes.get(body.get("code"));
      const verifier = body.get("code_verifier") ?? "";
      const challenge = createHash("sha256").update(verifier).digest("base64url");
      if (!record) {
        return oauthError(response, "invalid_grant", "Authorization code is invalid or already used", "unknown_authorization_code");
      }
      if (record.used) {
        return oauthError(response, "invalid_grant", "Authorization code is invalid or already used", "replayed_authorization_code");
      }
      if (record.redirectUri !== body.get("redirect_uri")) {
        return oauthError(response, "invalid_grant", "Authorization code is invalid or already used", "redirect_uri_mismatch");
      }
      if (record.challenge !== challenge) {
        return oauthError(response, "invalid_grant", "Authorization code is invalid or already used", "pkce_mismatch");
      }
      record.used = true;
      counters.code_exchange_count += 1;
      return json(response, 200, issueTokens(record.nonce));
    }
    if (body.get("grant_type") === "refresh_token") {
      const value = body.get("refresh_token");
      const record = value ? refreshTokens.get(value) : undefined;
      if (!record?.active) return oauthError(response, "invalid_grant", "Refresh token is invalid or revoked");
      record.active = false;
      counters.refresh_count += 1;
      counters.rotation_count += 1;
      return json(response, 200, issueTokens(record.nonce, record.generation + 1));
    }
    return oauthError(response, "unsupported_grant_type", "Grant type is not supported");
  }
  if (url.pathname === "/logout") {
    counters.logout_count += 1;
    const redirect = url.searchParams.get("post_logout_redirect_uri");
    if (redirect) {
      response.writeHead(302, { location: redirect });
      return response.end();
    }
    return json(response, 200, { ok: true });
  }
  if (url.pathname === "/test/status") return json(response, 200, counters);
  if (url.pathname === "/test/revoke-refresh" && request.method === "POST") {
    for (const record of refreshTokens.values()) record.active = false;
    return json(response, 200, { ok: true });
  }
  json(response, 404, { error: "not_found" });
});

const listenUrl = new URL(issuer);
server.listen(Number(listenUrl.port), listenUrl.hostname, () => {
  console.log(JSON.stringify({ event: "test_oidc_issuer_ready", issuer }));
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
