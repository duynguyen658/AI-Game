import { ApiError } from "./errors";

type BackendError = {
  error?: { code?: string; message?: string };
  detail?: string | { msg?: string }[];
  message?: string;
};

function errorMessage(body: BackendError | null, status: number) {
  if (body?.error?.message) return body.error.message;
  if (typeof body?.detail === "string") return body.detail;
  if (Array.isArray(body?.detail)) {
    return body.detail.map((item) => item.msg).filter(Boolean).join(". ");
  }
  if (body?.message) return body.message;
  return status === 503 ? "The service is currently unavailable" : "The request could not be completed";
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  if (!headers.has("x-correlation-id")) {
    headers.set("x-correlation-id", crypto.randomUUID());
  }
  const response = await fetch(`/api/backend${path}`, {
    ...init,
    headers,
    credentials: "same-origin",
  });
  const correlationId = response.headers.get("x-correlation-id") ?? undefined;
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as BackendError | null;
    if (response.status === 401 && typeof window !== "undefined") {
      window.location.assign("/session-expired");
    }
    throw new ApiError(
      errorMessage(body, response.status),
      response.status,
      body?.error?.code ?? `HTTP_${response.status}`,
      correlationId,
      body,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function jsonBody(value: unknown) {
  return JSON.stringify(value);
}
