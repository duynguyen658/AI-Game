import type { components } from "@/generated/openapi";
import { apiRequest } from "./client";
import type { AppliedTask } from "./data-analysis";

export type DocumentResult = components["schemas"]["DocumentProcessingResult"];

export const documentsApi = {
  list: (signal?: AbortSignal) =>
    apiRequest<AppliedTask[]>("/document-processing/tasks?limit=100", { signal }),
  create: (file: File) => {
    const body = new FormData();
    body.set("file", file);
    return apiRequest<AppliedTask>("/document-processing/tasks", { method: "POST", body });
  },
  get: (taskId: string, signal?: AbortSignal) =>
    apiRequest<AppliedTask>(`/document-processing/tasks/${taskId}`, { signal }),
  result: (taskId: string, signal?: AbortSignal) =>
    apiRequest<DocumentResult>(`/document-processing/tasks/${taskId}/result`, { signal }),
};
