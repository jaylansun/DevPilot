import { streamRequest } from "./stream_client";
import type { ProgressEvent } from "@/types/stream";
import { request } from "./http_client";
import type {
  WorkflowInfoVO,
  WorkflowRequestQO,
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
  onEvent: (event: ProgressEvent) => void = () => undefined,
) {
  return streamRequest(`/projects/${projectId}/assistant/runs/stream`, "workflow", body, signal, onEvent);
}
