import type { components } from "@/generated/openapi";
import { apiRequest } from "./client";

export type AppliedWorkflow = components["schemas"]["AppliedWorkflowDefinition"];
export const workflowsApi = {
  list: (signal?: AbortSignal) =>
    apiRequest<AppliedWorkflow[]>("/applied-workflows", { signal }),
};
