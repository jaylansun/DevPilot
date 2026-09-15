import { request } from "./http_client";
import type { RagAnswerVO, RagInfoVO, RagQuestionQO } from "@/types/api";

export function getKnowledgeInfo(projectId: string) {
  return request<RagInfoVO>(`/projects/${projectId}/knowledge`);
}

export function askKnowledge(
  projectId: string,
  body: RagQuestionQO,
  signal?: AbortSignal,
) {
  return request<RagAnswerVO>(`/projects/${projectId}/knowledge/questions`, {
    method: "POST",
    body,
    signal,
    timeoutMs: 75_000,
  });
}
