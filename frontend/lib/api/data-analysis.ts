import type { components } from "@/generated/openapi";
import { apiRequest } from "./client";

export type AppliedTask = components["schemas"]["AppliedTaskRead"];
export type DataAnalysisReport = components["schemas"]["DataAnalysisReport"];

export const dataAnalysisApi = {
  list: (signal?: AbortSignal) =>
    apiRequest<AppliedTask[]>("/data-analysis/tasks?limit=100", { signal }),
  create: (file: File) => {
    const body = new FormData();
    body.set("file", file);
    return apiRequest<AppliedTask>("/data-analysis/tasks", { method: "POST", body });
  },
  get: (taskId: string, signal?: AbortSignal) =>
    apiRequest<AppliedTask>(`/data-analysis/tasks/${taskId}`, { signal }),
  report: (taskId: string, signal?: AbortSignal) =>
    apiRequest<DataAnalysisReport>(`/data-analysis/tasks/${taskId}/report`, { signal }),
};
