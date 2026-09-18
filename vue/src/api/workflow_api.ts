import { request } from "./http_client";
import type {
  WorkflowInfoVO,
  WorkflowRequestQO,
  WorkflowResultVO,
} from "@/types/api";

export function getWorkflowInfo(projectId: string, signal?: AbortSignal) {
  return request<WorkflowInfoVO>(`/projects/${projectId}/assistant`, {
    signal,
  });
}

export function runWorkflow(
  projectId: string,
  body: WorkflowRequestQO,
  signal?: AbortSignal,
) {
  return request<WorkflowResultVO>(`/projects/${projectId}/assistant/runs`, {
    method: "POST",
    body,
    signal,
    timeoutMs: 75_000,
  });
}
