import { request } from "./http_client";
import { streamRequest } from "./stream_client";
import type { DraftUpdateQO, PlanDraftPageVO, PlanDraftVO, PlanRequestQO } from "@/types/api";
import type { ProgressEvent } from "@/types/stream";

const base = (projectId: string) => `/projects/${projectId}/planning/drafts`;

export function generateDraft(projectId: string, body: PlanRequestQO, signal: AbortSignal, onEvent: (event: ProgressEvent) => void) {
  return streamRequest(`${base(projectId)}/stream`, "draft", body, signal, onEvent);
}
export function listDrafts(projectId: string, offset = 0, signal?: AbortSignal) {
  return request<PlanDraftPageVO>(`${base(projectId)}?offset=${offset}&limit=20`, { signal });
}
export function getDraft(projectId: string, id: string, signal?: AbortSignal) {
  return request<PlanDraftVO>(`${base(projectId)}/${id}`, { signal });
}
export function updateDraft(projectId: string, id: string, body: DraftUpdateQO, signal?: AbortSignal) {
  return request<PlanDraftVO>(`${base(projectId)}/${id}`, { method: "PATCH", body, signal });
}
export function submitDraft(projectId: string, id: string, version: number, signal: AbortSignal, onEvent: (event: ProgressEvent) => void) {
  return streamRequest(`${base(projectId)}/${id}/submit/stream`, "approval", { version }, signal, onEvent);
}
