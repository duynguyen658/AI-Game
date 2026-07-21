import type { components } from "@/generated/openapi";
import { apiRequest, jsonBody } from "./client";

export type FeedbackCreate = components["schemas"]["UserFeedbackCreate"];
export type FeedbackRead = components["schemas"]["UserFeedbackRead"];

export const feedbackApi = {
  submit: (taskId: string, payload: FeedbackCreate) =>
    apiRequest<FeedbackRead>(`/task-runs/${taskId}/feedback`, { method: "POST", body: jsonBody(payload) }),
};
