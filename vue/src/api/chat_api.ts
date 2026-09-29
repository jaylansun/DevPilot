import type { ChatSessionVO, ChatSessionDetailVO, SessionMessageQO } from "@/types/api";
import { request } from "./http_client";
import { streamRequest } from "./stream_client";
import type { ChatInfoVO, ChatRequestQO } from "@/types/api";
import type { ProgressEvent } from "@/types/stream";

export function getChatInfo(projectId: string) {
  return request<ChatInfoVO>(`/projects/${projectId}/chat`);
}

export function sendChat(
  projectId: string,
  body: ChatRequestQO,
  signal?: AbortSignal,
  onEvent: (event: ProgressEvent) => void = () => undefined,
) {
  return streamRequest(`/projects/${projectId}/chat/messages/stream`, "chat", body, signal, onEvent);
}

const sessions = (projectId: string) => `/projects/${projectId}/chat/sessions`;
export const listChatSessions = (projectId: string, offset = 0) => request<ChatSessionVO[]>(`${sessions(projectId)}?offset=${offset}`);
export const createChatSession = (projectId: string) => request<ChatSessionVO>(sessions(projectId), { method: "POST" });
export const getChatSession = (projectId: string, id: string, before?: number) => request<ChatSessionDetailVO>(`${sessions(projectId)}/${id}${before ? `?before=${before}` : ""}`);
export const deleteChatSession = (projectId: string, id: string) => request<void>(`${sessions(projectId)}/${id}`, { method: "DELETE" });
export const sendSessionChat = (projectId: string, id: string, body: SessionMessageQO, signal: AbortSignal, onEvent: (event: ProgressEvent) => void) => streamRequest(`${sessions(projectId)}/${id}/messages/stream`, "chat", body, signal, onEvent);
