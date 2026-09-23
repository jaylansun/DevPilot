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
      if (event.kind === "knowledge") {
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
    // 规划服务 120 秒，流式收尾 130 秒；浏览器留出传输时间，避免提前掐断。
    timeoutMs: kind === "planning" || kind === "approval" || kind === "draft" ? 140_000 : 75_000,
    accept: "application/x-ndjson",
    readResponse: (response, combinedSignal) => readNDJSON(response, kind, onEvent, combinedSignal),
  });
}
