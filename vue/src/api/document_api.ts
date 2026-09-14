import type { DocumentListVO, DocumentVO } from "@/types/api";
import { request } from "./http_client";

const base = (projectId: string) =>
  `/projects/${encodeURIComponent(projectId)}/documents`;

export function listDocuments(projectId: string) {
  return request<DocumentListVO>(base(projectId));
}

export function uploadDocument(projectId: string, file: File) {
  const body = new FormData();
  body.append("file", file);
  return request<DocumentVO>(base(projectId), { method: "POST", body });
}

export function retryDocument(projectId: string, documentId: string) {
  return request<DocumentVO>(
    `${base(projectId)}/${encodeURIComponent(documentId)}/retry`,
    { method: "POST" },
  );
}

export function deleteDocument(projectId: string, documentId: string) {
  return request<DocumentVO>(
    `${base(projectId)}/${encodeURIComponent(documentId)}`,
    { method: "DELETE" },
  );
}
