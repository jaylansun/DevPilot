import { streamRequest } from "./stream_client";
import type { ProgressEvent } from "@/types/stream";
import { request } from "./http_client";
import type { RagInfoVO, RagQuestionQO } from "@/types/api";

export function getKnowledgeInfo(projectId: string) {
  return request<RagInfoVO>(`/projects/${projectId}/knowledge`);
}

export function askKnowledge(
  projectId: string,
  body: RagQuestionQO,
  signal?: AbortSignal,
  onEvent: (event: ProgressEvent) => void = () => undefined,
) {
  return streamRequest(`/projects/${projectId}/knowledge/questions/stream`, "knowledge", body, signal, onEvent);
}
