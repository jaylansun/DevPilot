import type {
  ProjectCreateQO,
  ProjectPageVO,
  ProjectUpdateQO,
  ProjectVO,
} from "@/types/api";
import { request } from "./http_client";

export function listProjects(offset = 0, limit = 9) {
  return request<ProjectPageVO>(
    `/projects?${new URLSearchParams({ offset: String(offset), limit: String(limit) })}`,
  );
}

export function getProject(id: string) {
  return request<ProjectVO>(`/projects/${encodeURIComponent(id)}`);
}

export function createProject(qo: ProjectCreateQO) {
  return request<ProjectVO>("/projects", { method: "POST", body: qo });
}

export function updateProject(id: string, qo: ProjectUpdateQO) {
  return request<ProjectVO>(`/projects/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: qo,
  });
}

export function deleteProject(id: string) {
  return request<void>(`/projects/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
}
