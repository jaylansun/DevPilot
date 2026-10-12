import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { configureAuth } from "@/api/http_client";
import { parseStreamEvent, readNDJSON, streamRequest } from "@/api/stream_client";
import { stepNames } from "@/types/stream";
import contract from "@/types/stream.contract.json";

const base = { version: 1, request_id: "test", seq: 1 };
const result = { mode: "live", answer: "中文🙂回答", sources: [], status: "insufficient_evidence" };
const token = { ...base, type: "token", text: "中文🙂" };
const final = { ...base, seq: 2, type: "final", kind: "knowledge", result };
const line = (event: unknown) => JSON.stringify(event) + "\n";
const encode = (text: string) => new TextEncoder().encode(text);
function response(chunks: Uint8Array[]) {
  return new Response(new ReadableStream({
    start(controller) { chunks.forEach((chunk) => controller.enqueue(chunk)); controller.close(); },
  }), { headers: { "Content-Type": "application/x-ndjson" } });
}

beforeEach(() => configureAuth(() => "test-token", () => undefined));
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

describe("NDJSON 客户端", () => {
  it("中文和 emoji 跨字节、跨行分包，多个事件粘包时都保持正确", async () => {
    const bytes = encode(line(token) + "\r\n" + line(final));
    const chunks = Array.from(bytes, (value) => new Uint8Array([value]));
    const received = vi.fn();
    await expect(readNDJSON(response(chunks), "knowledge", received)).resolves.toEqual(result);
    expect(received).toHaveBeenCalledExactlyOnceWith(token);
  });

  it("首个增量在 final 到来之前可见，final 后主动关闭读取器", async () => {
    let writer!: ReadableStreamDefaultController;
    const cancel = vi.fn();
    const res = new Response(new ReadableStream({ start(c) { writer = c; }, cancel }), {
      headers: { "Content-Type": "application/x-ndjson" },
    });
    const received = vi.fn();
    const pending = readNDJSON(res, "knowledge", received);
    writer.enqueue(encode(line(token)));
    await vi.waitFor(() => expect(received).toHaveBeenCalledTimes(1));
    writer.enqueue(encode(line(final)));
    await expect(pending).resolves.toEqual(result);
    expect(cancel).toHaveBeenCalledOnce();
  });

  it.each([
    "", line(token), "{bad}\n", line({ ...token, version: 2 }),
    line({ ...token, seq: 2 }), line(token) + line({ ...final, request_id: "another" }),
    line(token) + line({ ...final, kind: "planning" }),
    line(token) + line(final).trimEnd(), "x".repeat(1_000_001),
    line({ ...token, type: "unknown" }),
  ])("拒绝损坏、缺少终止事件、乱序或串线数据：%#", async (data) => {
    await expect(readNDJSON(response([encode(data)]), "knowledge", () => undefined))
      .rejects.toMatchObject({ code: "invalid_stream" });
  });

  it("流中的 error 保留稳定错误码与请求编号", async () => {
    const failure = { ...base, type: "error", status: 409, error: { code: "knowledge_changed", message: "资料已变化", request_id: "test", details: null } };
    await expect(readNDJSON(response([encode(line(failure))]), "knowledge", () => undefined))
      .rejects.toMatchObject({ code: "knowledge_changed", status: 409, requestId: "test" });
  });

  it("拒绝错误 content-type 与非法 UTF-8", async () => {
    await expect(readNDJSON(new Response("{}"), "knowledge", () => undefined)).rejects.toMatchObject({ code: "invalid_stream" });
    await expect(readNDJSON(response([new Uint8Array([255])]), "knowledge", () => undefined)).rejects.toMatchObject({ code: "invalid_stream" });
  });

  it("使用统一认证，处理开始流之前的 401", async () => {
    const unauthorized = vi.fn();
    configureAuth(() => "old-token", unauthorized);
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { code: "expired", message: "请登录" } }), { status: 401 }));
    vi.stubGlobal("fetch", fetch);
    await expect(streamRequest("/test", "knowledge", {}, undefined, () => undefined)).rejects.toMatchObject({ code: "expired" });
    expect(unauthorized).toHaveBeenCalledWith("old-token");
    expect(fetch.mock.calls[0]![1].headers.get("Authorization")).toBe("Bearer old-token");
  });

  it("流开始后取消会释放 reader，并且不会触发登录失效", async () => {
    const cancel = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(new ReadableStream({ cancel }), {
      headers: { "Content-Type": "application/x-ndjson" },
    })));
    const controller = new AbortController();
    const pending = streamRequest("/test", "knowledge", {}, controller.signal, () => undefined);
    await Promise.resolve();
    controller.abort();
    await expect(pending).rejects.toMatchObject({ code: "cancelled" });
    expect(cancel).toHaveBeenCalledOnce();
  });

  it("流读取也受整体超时约束", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(new ReadableStream(), {
      headers: { "Content-Type": "application/x-ndjson" },
    })));
    const pending = expect(streamRequest("/test", "knowledge", {}, undefined, () => undefined)).rejects.toMatchObject({ code: "timeout" });
    await vi.advanceTimersByTimeAsync(75_000);
    await pending;
  });

  it("前后端共享事件样例与步骤列表保持兼容", () => {
    expect(stepNames).toEqual(contract.steps);
    for (const event of contract.events) expect(parseStreamEvent(JSON.stringify(event))).toEqual(event);
  });

  it.each([{ version: 0 }, { status: "unknown" }, { conversation_id: 123 }, { plan: { persisted: false } }])("拒绝非法草案 final：%j", patch => {
    const sample = structuredClone(contract.events.find(event => event.type === "final" && event.kind === "draft")!);
    expect(() => parseStreamEvent(JSON.stringify({ ...sample, result: { ...sample.result, ...patch } }))).toThrow();
  });

  it.each(["planning", "approval", "draft"] as const)("%s 等待草案超过旧的 75 秒后仍可正常完成", async kind => {
    vi.useFakeTimers();
    let writer!: ReadableStreamDefaultController;
    const cancel = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(new ReadableStream({
      start(controller) { writer = controller; }, cancel,
    }), { headers: { "Content-Type": "application/x-ndjson" } })));
    const sample = contract.events.find(event => event.type === "final" && event.kind === kind)!;
    const pending = expect(streamRequest("/test", kind, {}, undefined, () => undefined)).resolves.toEqual(sample.result);
    await vi.advanceTimersByTimeAsync(80_000);
    expect(cancel).not.toHaveBeenCalled();
    writer.enqueue(encode(line({ ...sample, seq: 1 })));
    await pending;
    expect(cancel).toHaveBeenCalledOnce();
  });

  it.each(["planning", "approval", "draft"] as const)("%s 延长等待后仍受 140 秒总时限约束", async kind => {
    vi.useFakeTimers();
    const cancel = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(new ReadableStream({ cancel }), {
      headers: { "Content-Type": "application/x-ndjson" },
    })));
    const pending = expect(streamRequest("/test", kind, {}, undefined, () => undefined)).rejects.toMatchObject({ code: "timeout" });
    await vi.advanceTimersByTimeAsync(140_000);
    await pending;
    expect(cancel).toHaveBeenCalledOnce();
  });
});

describe("统一聊天工件与运行预算", () => {
  const plan = contract.events.find(event => event.type === "final" && event.kind === "draft")!.result!.plan;
  const check = {
    mode: "live", intent: "requirement_check", status: "reviewed", answer: "已检查需求", persisted: false,
    sources: [], tasks: [], tool_calls: [], report: { summary: "报告", insufficient_evidence: false, reviewed_source_ids: [], covered: [], missing: [], questions: [] },
    scope: { ready_documents: [], tasks: [], limitation: "仅检查相关片段", document_search_performed: true, board_read: true },
  };
  const artifactAnswer = () => ({ mode: "live", basis: "project", status: "answered", answer: "草案和报告已保存", sources: [], tasks: [],
    tool_calls: [{ name: "generate_task_plan", status: "success", item_count: 1 }, { name: "check_requirements", status: "success", item_count: 1 }],
    artifacts: [{ type: "task_plan", goal: "完善项目", result: plan, draft_id: "saved-draft", draft_version: 2 }, { type: "requirement_check", result: check }],
  });
  it("同一聊天final接受保存草案和需求报告，不需要改变流kind", () => {
    const event = { ...base, type: "final", kind: "chat", result: artifactAnswer() };
    expect(parseStreamEvent(JSON.stringify(event))).toEqual(event);
  });
  it("旧聊天没有artifacts字段时仍可读取", () => {
    const event = { ...base, type: "final", kind: "chat", result: { mode: "live", basis: "general", status: "answered", answer: "你好", sources: [], tasks: [], tool_calls: [] } };
    expect(parseStreamEvent(JSON.stringify(event))).toEqual(event);
  });
  it.each([
    { type: "unknown", result: plan },
    { type: "task_plan", goal: "目标", result: plan, draft_id: "saved-draft", draft_version: 0 },
    { type: "requirement_check", result: { ...check, report: { covered: [], missing: null, questions: [] } } },
    { type: "task_plan", goal: "目标", result: { ...plan, proposal: { summary: "缺少任务字段", assumptions: [], risks: [], tasks: [{}] } }, draft_id: null, draft_version: null },
  ])("损坏的工件不会传入结果侧栏：%j", artifact => {
    const result = { ...artifactAnswer(), artifacts: [artifact] };
    expect(() => parseStreamEvent(JSON.stringify({ ...base, type: "final", kind: "chat", result }))).toThrow();
  });
  it("统一聊天超过旧的120秒预算后仍能收到草案", async () => {
    vi.useFakeTimers();
    let writer!: ReadableStreamDefaultController;
    const cancel = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(new ReadableStream({ start(controller) { writer = controller; }, cancel }), { headers: { "Content-Type": "application/x-ndjson" } })));
    const answer = artifactAnswer();
    const pending = expect(streamRequest("/test", "chat", {}, undefined, () => undefined)).resolves.toEqual(answer);
    await vi.advanceTimersByTimeAsync(230_000);
    expect(cancel).not.toHaveBeenCalled();
    writer.enqueue(encode(line({ ...base, type: "final", kind: "chat", result: answer })));
    await pending;
  });
  it("统一聊天仍受240秒总时限约束", async () => {
    vi.useFakeTimers();
    const cancel = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(new ReadableStream({ cancel }), { headers: { "Content-Type": "application/x-ndjson" } })));
    const pending = expect(streamRequest("/test", "chat", {}, undefined, () => undefined)).rejects.toMatchObject({ code: "timeout" });
    await vi.advanceTimersByTimeAsync(240_000);
    await pending;
    expect(cancel).toHaveBeenCalledOnce();
  });
});
