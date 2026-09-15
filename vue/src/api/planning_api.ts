import { request } from "./http_client";
import type { PlanInfoVO, PlanRequestQO, PlanResultVO } from "@/types/api";

export function getPlanningInfo(projectId: string, signal?: AbortSignal) {
  return request<PlanInfoVO>(`/projects/${projectId}/planning`, { signal });
}

export function proposeTasks(
  projectId: string,
  body: PlanRequestQO,
  signal?: AbortSignal,
) {
  return request<PlanResultVO>(`/projects/${projectId}/planning/proposals`, {
    method: "POST",
    body,
    signal,
    timeoutMs: 75_000,
  });
}
