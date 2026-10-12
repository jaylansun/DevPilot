import { ApiError, request } from "./http_client";
import { stepNames, type ProgressEvent, type Results, type RunKind, type StreamEvent } from "@/types/stream";

const invalid = () => new ApiError("流式数据不完整或格式不正确，请重试", 502, "invalid_stream");
const object = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === "object" && !Array.isArray(value);

function validApproval(value: unknown): boolean {
  return object(value) && typeof value.id === "string" && typeof value.conversation_id === "string" &&
    typeof value.project_id === "string" && typeof value.goal === "string" &&
    ["pending", "processing", "approved", "rejected"].includes(value.status as string) &&
    object(value.plan) && object(value.plan.proposal) && Array.isArray(value.plan.proposal.tasks) &&
    Array.isArray(value.plan.sources) && Array.isArray(value.created_tasks);
}

function validArtifact(value: unknown): boolean {
  if (!object(value) || !object(value.result)) return false;
  const result = value.result;
  if (!["mock", "live"].includes(result.mode as string) || !Array.isArray(result.sources) || !Array.isArray(result.tool_calls) ||
      !result.sources.every(source => object(source) && Number.isSafeInteger(source.source_id) && (source.source_id as number) > 0 &&
        typeof source.document_id === "string" && typeof source.filename === "string" && typeof source.heading === "string" &&
        typeof source.text === "string" && Number.isSafeInteger(source.chunk_index) && (source.chunk_index as number) >= 0)) return false;
  if (value.type === "task_plan") {
    return typeof value.goal === "string" && (value.draft_id == null || typeof value.draft_id === "string") &&
      (value.draft_version == null || (Number.isSafeInteger(value.draft_version) && (value.draft_version as number) > 0)) &&
      object(result.proposal) && typeof result.proposal.summary === "string" && Array.isArray(result.proposal.assumptions) &&
      result.proposal.assumptions.every(item => typeof item === "string") && Array.isArray(result.proposal.risks) &&
      result.proposal.risks.every(item => typeof item === "string") && Array.isArray(result.proposal.tasks) && result.proposal.tasks.every(task =>
        object(task) && typeof task.draft_id === "string" && typeof task.title === "string" && typeof task.description === "string" &&
        typeof task.acceptance_criteria === "string" && Number.isInteger(task.priority) && Array.isArray(task.dependencies) &&
        task.dependencies.every(item => typeof item === "string") && Array.isArray(task.source_ids) && task.source_ids.every(id => Number.isSafeInteger(id) && (id as number) > 0));
  }
  if (value.type === "requirement_check") {
    if (typeof result.answer !== "string" || !["knowledge_question", "task_lookup", "requirement_check", "clarify"].includes(result.intent as string) ||
        !["reviewed", "answered", "insufficient_evidence", "demo", "clarification_needed"].includes(result.status as string) ||
        !Array.isArray(result.tasks) || !object(result.scope) ||
        !Array.isArray(result.scope.tasks) || !Array.isArray(result.scope.ready_documents) || typeof result.scope.limitation !== "string") return false;
    return result.report === null || result.report === undefined || (object(result.report) &&
      Array.isArray(result.report.covered) && Array.isArray(result.report.missing) && Array.isArray(result.report.questions) &&
      result.report.covered.every(item => object(item) && typeof item.requirement === "string" && typeof item.explanation === "string" && Array.isArray(item.source_ids) && Array.isArray(item.task_ids)) &&
      result.report.missing.every(item => object(item) && typeof item.requirement === "string" && typeof item.explanation === "string" && Array.isArray(item.source_ids)) &&
      result.report.questions.every(item => object(item) && typeof item.question === "string" && typeof item.reason === "string" && Array.isArray(item.source_ids)));
  }
  return false;
}

export function parseStreamEvent(line: string): StreamEvent {
  let event: unknown;
  try { event = JSON.parse(line); } catch { throw invalid(); }
  if (!object(event) || event.version !== 1 || !Number.isSafeInteger(event.seq) ||
      (event.seq as number) < 1 || typeof event.request_id !== "string") throw invalid();
  switch (event.type) {
    case "approval_required":
      if (!validApproval(event.approval) || (event.approval as Record<string, unknown>).status !== "pending") throw invalid();
      break;
    case "node": case "tool":
      if (typeof event.id !== "string" || !stepNames.includes(event.name as never) ||
          !["started", "completed", "failed"].includes(event.status as string)) throw invalid();
      break;
    case "token":
      if (typeof event.text !== "string" || !event.text.length || event.text.length > 4000) throw invalid();
      break;
    case "error":
      if (!Number.isInteger(event.status) || (event.status as number) < 400 || (event.status as number) > 599 ||
          !object(event.error) || typeof event.error.code !== "string" || typeof event.error.message !== "string" ||
          event.error.request_id !== event.request_id) throw invalid();
      break;
    case "final": {
      const result = event.result;
      if (event.kind === "approval") {
        if (!validApproval(result)) throw invalid();
        break;
      }
      if (event.kind === "draft") {
        if (!object(result) || typeof result.id !== "string" || typeof result.project_id !== "string" ||
            typeof result.goal !== "string" || !Number.isSafeInteger(result.version) || (result.version as number) < 1 ||
            !["draft", "submitted"].includes(result.status as string) ||
            !(result.conversation_id === null || typeof result.conversation_id === "string") ||
            !object(result.plan) || result.plan.persisted !== true ||
            !["mock", "live"].includes(result.plan.mode as string) || !Array.isArray(result.plan.sources) ||
            !object(result.plan.proposal) || !Array.isArray(result.plan.proposal.tasks)) throw invalid();
        break;
      }
      if (!object(result) || !["mock", "live"].includes(result.mode as string) || !Array.isArray(result.sources)) throw invalid();
      if (event.kind === "chat") {
        if (typeof result.answer !== "string" || !["answered", "insufficient_evidence", "demo"].includes(result.status as string) ||
            !["general", "project"].includes(result.basis as string) || !Array.isArray(result.tasks) || !Array.isArray(result.tool_calls) ||
            !result.sources.every(source => object(source) && Number.isSafeInteger(source.source_id) && (source.source_id as number) > 0 &&
              typeof source.document_id === "string" && typeof source.filename === "string" && typeof source.heading === "string" &&
              typeof source.text === "string" && Number.isSafeInteger(source.chunk_index) && (source.chunk_index as number) >= 0) ||
            !result.tasks.every(task => object(task) && typeof task.id === "string" && typeof task.title === "string" &&
              ["todo", "in_progress", "done"].includes(task.status as string) && Number.isInteger(task.priority) &&
              typeof task.description === "string" && typeof task.acceptance_criteria === "string" &&
              typeof task.description_truncated === "boolean" && typeof task.acceptance_criteria_truncated === "boolean") ||
            !result.tool_calls.every(call => object(call) && ["search_documents", "read_task_board", "generate_task_plan", "check_requirements"].includes(call.name as string) &&
              ["success", "empty"].includes(call.status as string) && Number.isSafeInteger(call.item_count) && (call.item_count as number) >= 0) ||
            (result.artifacts !== undefined && (!Array.isArray(result.artifacts) || !result.artifacts.every(validArtifact))) ||
            (result.basis === "general" && (result.sources.length > 0 || result.tasks.length > 0 || result.tool_calls.length > 0 ||
              (Array.isArray(result.artifacts) && result.artifacts.length > 0)))) throw invalid();
      } else if (event.kind === "knowledge") {
        if (typeof result.answer !== "string" || !["answered", "insufficient_evidence"].includes(result.status as string)) throw invalid();
      } else if (event.kind === "planning") {
        if (!object(result.proposal) || !Array.isArray(result.proposal.tasks)) throw invalid();
      } else if (event.kind === "workflow") {
        if (typeof result.answer !== "string" || !object(result.scope) || !Array.isArray(result.tasks)) throw invalid();
      } else throw invalid();
      break;
    }
    default: throw invalid();
  }
  return event as StreamEvent;
}

export async function readNDJSON<K extends RunKind>(
  response: Response, kind: K, onEvent: (event: ProgressEvent) => void, signal?: AbortSignal,
): Promise<Results[K]> {
  if (!response.headers.get("Content-Type")?.toLowerCase().startsWith("application/x-ndjson") || !response.body)
    throw invalid();
  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  let buffer = "", seq = 0, requestId: string | undefined;
  // 限制单行和总数据量；不把任意长、不带换行的响应一直留在内存里。
  let bytes = 0;
  const cancel = () => { void reader.cancel().catch(() => undefined); };
  signal?.addEventListener("abort", cancel, { once: true });
  try {
    while (true) {
      if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
      const { value, done } = await reader.read();
      if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
      bytes += value?.byteLength ?? 0;
      if (bytes > 4_000_000) throw invalid();
      try { buffer += decoder.decode(value, { stream: !done }); } catch { throw invalid(); }
      let newline: number;
      while ((newline = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        if (!line) continue;
        if (line.length > 1_000_000) throw invalid();
        const event = parseStreamEvent(line);
        if (event.seq !== seq + 1 || (requestId !== undefined && event.request_id !== requestId)) throw invalid();
        seq = event.seq;
        requestId = event.request_id;
        if (event.type === "error")
          throw new ApiError(event.error.message, event.status, event.error.code, event.request_id);
        if (event.type === "final") {
          if (event.kind !== kind) throw invalid();
          return event.result as Results[K];
        }
        onEvent(event);
      }
      if (buffer.length > 1_000_000 || done) throw invalid();
    }
  } finally {
    signal?.removeEventListener("abort", cancel);
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

export function streamRequest<K extends RunKind>(
  path: string, kind: K, body: unknown, signal: AbortSignal | undefined,
  onEvent: (event: ProgressEvent) => void,
) {
  return request<Results[K]>(path, {
    method: "POST", body, signal,
    // 统一聊天可能串行查询、规划和检查，给服务端 230 秒预算留出传输时间。
    timeoutMs: kind === "planning" || kind === "approval" || kind === "draft" ? 140_000 : kind === "chat" ? 240_000 : 75_000,
    accept: "application/x-ndjson",
    readResponse: (response, combinedSignal) => readNDJSON(response, kind, onEvent, combinedSignal),
  });
}
