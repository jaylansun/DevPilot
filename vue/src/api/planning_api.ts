import { streamRequest } from "./stream_client";
import type { ProgressEvent } from "@/types/stream";
import { request } from "./http_client";
import type { PlanInfoVO, PlanRequestQO } from "@/types/api";

export function getPlanningInfo(projectId: string, signal?: AbortSignal) {
  return request<PlanInfoVO>(`/projects/${projectId}/planning`, { signal });
}

export function proposeTasks(
  projectId: string,
  body: PlanRequestQO,
  signal?: AbortSignal,
  onEvent: (event: ProgressEvent) => void = () => undefined,
) {
  return streamRequest(`/projects/${projectId}/planning/proposals/stream`, "planning", body, signal, onEvent);
}
