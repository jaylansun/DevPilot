import { request } from "./http_client";
import { streamRequest } from "./stream_client";
import type { ApprovalDecisionQO, ApprovalPageVO, ApprovalVO, ConversationVO } from "@/types/api";
import type { ProgressEvent } from "@/types/stream";

export function createConversation(projectId: string, goal: string, signal?: AbortSignal) {
  return request<ConversationVO>(`/projects/${projectId}/conversations`, { method: "POST", body: { goal }, signal });
}
export function listConversations(projectId: string, offset = 0, signal?: AbortSignal) {
  return request<ConversationVO[]>(`/projects/${projectId}/conversations?offset=${offset}&limit=20`, { signal });
}
export function runConversation(id: string, signal: AbortSignal, onEvent: (event: ProgressEvent) => void) {
  return streamRequest(`/conversations/${id}/runs/stream`, "approval", undefined, signal, onEvent);
}
export function listApprovals(status: string, offset = 0, signal?: AbortSignal) {
  return request<ApprovalPageVO>(`/approvals?offset=${offset}&limit=20${status ? `&status=${encodeURIComponent(status)}` : ""}`, { signal });
}
export function getApproval(id: string, signal?: AbortSignal) {
  return request<ApprovalVO>(`/approvals/${id}`, { signal });
}
export function decideApproval(id: string, body: ApprovalDecisionQO, signal: AbortSignal, onEvent: (event: ProgressEvent) => void) {
  return streamRequest(`/approvals/${id}/decide/stream`, "approval", body, signal, onEvent);
}
