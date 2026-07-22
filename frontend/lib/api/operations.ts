import type { components } from "@/generated/openapi";
import { apiRequest } from "./client";

export type BusinessImpact = components["schemas"]["BusinessImpactAnalytics"];
export type OperationsSummary = components["schemas"]["OperationsSummary"];
export type JobStatus = components["schemas"]["JobStatusRead"];
export type Job = components["schemas"]["JobRead"];
export type Alert = components["schemas"]["AlertRead"];

export type HealthReport = {
  status: string;
  version: string;
  timestamp: string;
  checks?: Record<string, unknown>;
};

export type ImpactFilters = {
  task_type?: string;
  department?: string;
  provider?: string;
  model?: string;
  prompt_version_id?: string;
  created_from?: string;
  created_to?: string;
};

function queryString(filters: ImpactFilters) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => { if (value) params.set(key, value); });
  const query = params.toString();
  return query ? `?${query}` : "";
}

export const operationsApi = {
  impact: (signal?: AbortSignal) =>
    apiRequest<BusinessImpact>("/analytics/business-impact", { signal }),
  filteredImpact: (filters: ImpactFilters, signal?: AbortSignal) =>
    apiRequest<BusinessImpact>(`/analytics/business-impact${queryString(filters)}`, { signal }),
  summary: (signal?: AbortSignal) =>
    apiRequest<OperationsSummary>("/operations/summary", { signal }),
  jobStatus: (jobId: string, signal?: AbortSignal) =>
    apiRequest<JobStatus>(`/jobs/${jobId}/status`, { signal }),
  jobs: (signal?: AbortSignal) => apiRequest<Job[]>("/jobs?limit=100", { signal }),
  job: (jobId: string, signal?: AbortSignal) => apiRequest<Job>(`/jobs/${jobId}`, { signal }),
  retryJob: (jobId: string) => apiRequest<Job>(`/jobs/${jobId}/retry`, { method: "POST" }),
  cancelJob: (jobId: string) => apiRequest<Job>(`/jobs/${jobId}/cancel`, { method: "POST" }),
  alerts: (signal?: AbortSignal) => apiRequest<Alert[]>("/alerts?limit=100", { signal }),
  alert: (alertId: string, signal?: AbortSignal) => apiRequest<Alert>(`/alerts/${alertId}`, { signal }),
  acknowledgeAlert: (alertId: string) => apiRequest<Alert>(`/alerts/${alertId}/acknowledge`, { method: "POST" }),
  resolveAlert: (alertId: string) => apiRequest<Alert>(`/alerts/${alertId}/resolve`, { method: "POST" }),
  health: (signal?: AbortSignal) => apiRequest<HealthReport>("/health", { signal }),
  readiness: (signal?: AbortSignal) => apiRequest<HealthReport>("/ready", { signal }),
  reconcileJobs: () => apiRequest<{ reclaimed: number }>("/operations/jobs/reconcile", { method: "POST" }),
  reconcileAlerts: () => apiRequest<Record<string, number>>("/operations/alerts/reconcile", { method: "POST" }),
  reconcileOutbox: () => apiRequest<{ processed: number }>("/operations/outbox/reconcile", { method: "POST" }),
  reconcileMemory: () => apiRequest<{ processed: number }>("/operations/memory/reconcile", { method: "POST" }),
};

export const terminalJobStatuses = new Set([
  "SUCCEEDED",
  "FAILED",
  "CANCELLED",
  "DEAD_LETTER",
]);
