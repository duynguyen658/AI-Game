import type { components } from "@/generated/openapi";
import { apiRequest, jsonBody } from "./client";
export type PromptTemplate = components["schemas"]["PromptTemplateRead"];
export type PromptVersion = components["schemas"]["PromptVersionRead"];
export type PromptVersionCreate = components["schemas"]["PromptVersionCreate"];
export const promptsApi = {
  list: (signal?: AbortSignal) => apiRequest<PromptTemplate[]>("/prompt-templates?limit=100", { signal }),
  getTemplate: (id: string, signal?: AbortSignal) => apiRequest<PromptTemplate>(`/prompt-templates/${id}`, { signal }),
  versions: (id: string, signal?: AbortSignal) => apiRequest<PromptVersion[]>(`/prompt-templates/${id}/versions?limit=100`, { signal }),
  createVersion: (id: string, payload: PromptVersionCreate) => apiRequest<PromptVersion>(`/prompt-templates/${id}/versions`, { method: "POST", body: jsonBody(payload) }),
  getVersion: (id: string, signal?: AbortSignal) => apiRequest<PromptVersion>(`/prompt-versions/${id}`, { signal }),
  transition: (id: string, action: "submit-testing" | "approve" | "retire", status: string) => apiRequest<PromptVersion>(`/prompt-versions/${id}/${action}`, { method: "POST", body: jsonBody({ expected_status: status }) }),
  activate: (id: string, status: string, templateVersion: number) => apiRequest<PromptVersion>(`/prompt-versions/${id}/activate`, { method: "POST", body: jsonBody({ expected_status: status, expected_template_version: templateVersion }) }),
};
