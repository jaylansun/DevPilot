import type {
  TaskCreateQO,
  TaskUpdateQO,
  TaskVO,
  TaskPageVO,
  TaskStatus,
} from "@/types/api";
import { request } from "./http_client";

type TaskListQuery = {
  offset?: number;
  limit?: number;
  status?: TaskStatus;
  priority?: number;
};

function taskPath(projectId: string, taskId?: string) {
  const base = `/projects/${encodeURIComponent(projectId)}/tasks`;
  return taskId ? `${base}/${encodeURIComponent(taskId)}` : base;
}

export function listTasks(projectId: string, query: TaskListQuery = {}) {
  const params = new URLSearchParams({
    offset: String(query.offset ?? 0),
    limit: String(query.limit ?? 8),
  });
  if (query.status) params.set("status", query.status);
  if (query.priority !== undefined)
    params.set("priority", String(query.priority));
  return request<TaskPageVO>(`${taskPath(projectId)}?${params}`);
}

export function getTask(projectId: string, taskId: string) {
  return request<TaskVO>(taskPath(projectId, taskId));
}

export function createTask(projectId: string, qo: TaskCreateQO) {
  return request<TaskVO>(taskPath(projectId), { method: "POST", body: qo });
}

export function updateTask(
  projectId: string,
  taskId: string,
  qo: TaskUpdateQO,
) {
  return request<TaskVO>(taskPath(projectId, taskId), {
    method: "PATCH",
    body: qo,
  });
}

export function deleteTask(projectId: string, taskId: string) {
  return request<void>(taskPath(projectId, taskId), { method: "DELETE" });
}
