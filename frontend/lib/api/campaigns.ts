import type { components } from "@/generated/openapi";
import { apiRequest, jsonBody } from "./client";

export type CampaignCreate = components["schemas"]["CampaignCreate"];
export type CampaignRecord = components["schemas"]["CampaignRecord"];
export type WorkflowRun = components["schemas"]["WorkflowRun"];
export type WorkflowEnqueue = components["schemas"]["WorkflowEnqueueResponse"];
export type ApprovalRequest = components["schemas"]["ApprovalRequest"];
export type ApprovalRecord = components["schemas"]["ApprovalRecord"];
export type TimelineEvent = components["schemas"]["TimelineEvent"];

export const campaignsApi = {
  list: (signal?: AbortSignal) =>
    apiRequest<CampaignRecord[]>("/campaigns?limit=100", { signal }),
  get: (campaignId: string, signal?: AbortSignal) =>
    apiRequest<CampaignRecord>(`/campaigns/${encodeURIComponent(campaignId)}`, { signal }),
  create: (payload: CampaignCreate) =>
    apiRequest<CampaignRecord>("/campaigns", { method: "POST", body: jsonBody(payload) }),
  createWorkflow: (campaignId: string) =>
    apiRequest<WorkflowRun>(`/workflows/campaigns/${encodeURIComponent(campaignId)}`, { method: "POST" }),
  getWorkflow: (workflowId: string, signal?: AbortSignal) =>
    apiRequest<WorkflowRun>(`/workflows/${workflowId}`, { signal }),
  runWorkflow: (workflowId: string) =>
    apiRequest<WorkflowEnqueue>(`/workflows/${workflowId}/run`, { method: "POST" }),
  timeline: (workflowId: string, signal?: AbortSignal) =>
    apiRequest<TimelineEvent[]>(`/operations/workflows/${workflowId}/timeline`, { signal }),
  decide: (payload: ApprovalRequest) =>
    apiRequest<ApprovalRecord>("/approvals", { method: "POST", body: jsonBody(payload) }),
};
