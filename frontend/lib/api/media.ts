import type { components } from "@/generated/openapi";
import { apiRequest, jsonBody } from "./client";

export type MediaAsset = components["schemas"]["MediaAssetRead"];
export type ImageRequest = components["schemas"]["ImageGenerationRequest"];
export type MediaReview = components["schemas"]["MediaReviewRequest"];
export type StoryboardRequest = components["schemas"]["VideoStoryboardRequest"];
export type Storyboard = components["schemas"]["VideoStoryboard"];

export const mediaApi = {
  createImage: (payload: ImageRequest) =>
    apiRequest<MediaAsset>("/media/images", {
      method: "POST",
      headers: { "x-idempotency-key": crypto.randomUUID() },
      body: jsonBody(payload),
    }),
  get: (assetId: string, signal?: AbortSignal) =>
    apiRequest<MediaAsset>(`/media/assets/${assetId}`, { signal }),
  review: (assetId: string, decision: "APPROVE" | "REJECT", payload: MediaReview) =>
    apiRequest<MediaAsset>(`/media/assets/${assetId}/${decision === "APPROVE" ? "approve" : "reject"}`, {
      method: "POST",
      body: jsonBody({ ...payload, decision }),
    }),
  createStoryboard: (payload: StoryboardRequest) =>
    apiRequest<MediaAsset>("/media/video-storyboards", { method: "POST", body: jsonBody(payload) }),
  storyboard: (assetId: string, signal?: AbortSignal) =>
    apiRequest<Storyboard>(`/media/video-storyboards/${assetId}`, { signal }),
};
