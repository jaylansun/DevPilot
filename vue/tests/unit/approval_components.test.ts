import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createApp, nextTick, reactive, type App, type Component } from "vue";
import { createPinia } from "pinia";
import { ElButton } from "element-plus";
import PlanningApprovals from "@/components/PlanningApprovals.vue";
import ReviewerView from "@/views/ReviewerView.vue";
import RunTrace from "@/components/RunTrace.vue";
import ApprovalDetails from "@/components/ApprovalDetails.vue";
import { useAuthStore } from "@/stores/auth_store";
import * as api from "@/api/approval_api";
import { ApiError } from "@/api/http_client";
import contract from "@/types/stream.contract.json";
import type { ApprovalVO, ConversationVO } from "@/types/api";
import type { TraceEvent } from "@/types/stream";

vi.mock("@/api/approval_api", () => ({
  createConversation: vi.fn(), listConversations: vi.fn(), runConversation: vi.fn(),
  listApprovals: vi.fn(), getApproval: vi.fn(), decideApproval: vi.fn(),
}));

function approval(): ApprovalVO {
  const sample = contract.events.find(event => event.type === "final" && event.kind === "approval");
  return structuredClone(sample!.result) as ApprovalVO;
}
function conversation(result?: ApprovalVO): ConversationVO {
  const sample = approval();
  return { id: sample.conversation_id, project_id: sample.project_id, goal: sample.goal,
    status: result?.status ?? "interrupted", approval: result ?? null };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

let app: App | undefined;
let root: HTMLDivElement;
function mount(component: Component, props = {}) {
  root = document.createElement("div"); document.body.append(root);
  const pinia = createPinia();
  app = createApp(component, props).use(pinia);
  app.component("ElButton", ElButton);
  useAuthStore(pinia).user = { id: "reviewer", username: "审核", role: "reviewer",
    created_at: "2026-09-22T00:00:00Z", updated_at: "2026-09-22T00:00:00Z" };
  app.mount(root);
}
function button(text: string) {
  const found = [...root.querySelectorAll("button")].find(b => b.textContent?.trim() === text);
  expect(found, `按钮：${text}`).toBeDefined();
  return found!;
}
async function click(text: string) { button(text).click(); await nextTick(); }
async function openReview(value = approval()) {
  vi.mocked(api.listApprovals).mockResolvedValue({ items: [value], total: 1, offset: 0, limit: 20 });
  vi.mocked(api.getApproval).mockResolvedValue(value);
  mount(ReviewerView);
  await vi.waitFor(() => expect(root.querySelector("button[aria-pressed] ")).not.toBeNull());
  (root.querySelector("button[aria-pressed]") as HTMLButtonElement).click();
  await nextTick();
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.listConversations).mockResolvedValue([]);
});
afterEach(() => { app?.unmount(); app = undefined; root?.remove(); });

describe("成员提交与恢复", () => {
  it("恢复中断记录复用会话，连续点击只启动一次，成功后展示已保存方案", async () => {
    const done = deferred<ApprovalVO>();
    const record = conversation();
    vi.mocked(api.listConversations).mockResolvedValue([record]);
    vi.mocked(api.runConversation).mockReturnValue(done.promise);
    mount(PlanningApprovals, { projectId: record.project_id, goal: "目标", disabled: false });
    await vi.waitFor(() => expect(root.textContent).toContain("生成中断，可继续"));
    await click("继续处理");
    await click("继续处理");
    expect(api.createConversation).not.toHaveBeenCalled();
    expect(api.runConversation).toHaveBeenCalledTimes(1);
    expect(api.runConversation).toHaveBeenCalledWith(record.id, expect.any(AbortSignal), expect.any(Function));
    vi.mocked(api.listConversations).mockResolvedValue([conversation(approval())]);
    done.resolve(approval());
    await vi.waitFor(() => expect(root.querySelector('[role="status"]')?.textContent).toBe("等待审批"));
  });

  it("生成超时保留会话和请求编号，重试继续原记录", async () => {
    const record = conversation();
    vi.mocked(api.listConversations).mockResolvedValue([record]);
    vi.mocked(api.runConversation).mockRejectedValueOnce(new ApiError("任务规划超时", 504, "planning_timeout", "request-timeout"));
    mount(PlanningApprovals, { projectId: record.project_id, goal: "订单目标", disabled: false });
    await vi.waitFor(() => expect(root.textContent).toContain("继续处理"));
    vi.mocked(api.listConversations).mockResolvedValue([record]);
    await click("继续处理");
    await vi.waitFor(() => expect(root.querySelector('[role="alert"]')?.textContent).toContain("request-timeout"));
    vi.mocked(api.runConversation).mockResolvedValue(approval());
    await click("继续处理");
    await vi.waitFor(() => expect(root.querySelector('[role="status"]')?.textContent).toBe("等待审批"));
    expect(api.createConversation).not.toHaveBeenCalled();
    expect(api.runConversation).toHaveBeenCalledTimes(2);
  });

  it("停止等待取消请求并刷新记录，卸载后迟到结果不启动新的列表请求", async () => {
    const record = conversation();
    vi.mocked(api.listConversations).mockResolvedValue([record]);
    vi.mocked(api.runConversation).mockImplementation((_id, signal) => new Promise((_, reject) => {
      signal.addEventListener("abort", () => reject(new DOMException("cancel", "AbortError")), { once: true });
    }));
    mount(PlanningApprovals, { projectId: record.project_id, goal: "目标", disabled: false });
    await vi.waitFor(() => expect(root.textContent).toContain("继续处理")); await click("继续处理");
    await vi.waitFor(() => expect(api.runConversation).toHaveBeenCalledTimes(1));
    await click("停止等待");
    await vi.waitFor(() => expect(root.textContent).toContain("请刷新后继续该记录"));
    const late = deferred<ApprovalVO>();
    vi.mocked(api.runConversation).mockReturnValueOnce(late.promise);
    await click("继续处理");
    await vi.waitFor(() => expect(api.runConversation).toHaveBeenCalledTimes(2));
    const signal = vi.mocked(api.runConversation).mock.calls[1]![1];
    app!.unmount(); app = undefined;
    const calls = vi.mocked(api.listConversations).mock.calls.length;
    expect(signal.aborted).toBe(true);
    late.resolve(approval()); await nextTick(); await nextTick();
    expect(api.listConversations).toHaveBeenCalledTimes(calls);
  });
});

describe("人工审批", () => {
  it("编辑时保留原方案，提交编辑值，成功后关闭审批操作", async () => {
    const original = approval();
    await openReview(original);
    await click("修改任务方案");
    const title = root.querySelector('fieldset input:not([type="checkbox"])') as HTMLInputElement;
    title.value = "人工修改标题"; title.dispatchEvent(new Event("input", { bubbles: true }));
    await nextTick();
    expect(original.plan.proposal.tasks[0]!.title).toBe("实现下单校验");
    const approved = { ...approval(), status: "approved" as const };
    vi.mocked(api.decideApproval).mockResolvedValue(approved);
    vi.mocked(api.getApproval).mockResolvedValue(approved);
    await click("修改后批准并加入看板");
    await vi.waitFor(() => expect(api.decideApproval).toHaveBeenCalledTimes(1));
    const body = vi.mocked(api.decideApproval).mock.calls[0]![1];
    expect(body.action).toBe("edit_and_approve");
    expect(body.proposal?.tasks[0]?.title).toBe("人工修改标题");
    await vi.waitFor(() => expect(root.textContent).toContain("已批准并加入看板"));
    expect(root.textContent).not.toContain("拒绝方案");
  });

  it("资料冲突展示错误与请求编号，仍保留待审方案供修改或拒绝", async () => {
    await openReview();
    vi.mocked(api.decideApproval).mockRejectedValue(new ApiError("资料内容已变化", 409, "approval_documents_changed", "request-conflict"));
    await click("批准并加入看板");
    await vi.waitFor(() => expect(root.querySelector('[role="alert"]')?.textContent).toContain("request-conflict"));
    await vi.waitFor(() => expect(button("拒绝方案").disabled).toBe(false));
    expect(root.textContent).toContain("实现下单校验");
  });

  it("拒绝发送明确决定，完成后不展示创建任务的成功信息", async () => {
    await openReview();
    const rejected = { ...approval(), status: "rejected" as const };
    vi.mocked(api.decideApproval).mockResolvedValue(rejected);
    vi.mocked(api.getApproval).mockResolvedValue(rejected);
    await click("拒绝方案");
    expect(api.decideApproval).toHaveBeenCalledWith(rejected.id, { action: "reject" }, expect.any(AbortSignal), expect.any(Function));
    await vi.waitFor(() => expect(root.querySelector('[role="status"]')?.textContent).toBe("已拒绝"));
    expect(root.textContent).not.toContain("已创建");
  });

  it("审批中停止等待不会显示为撤回，而是刷新后允许继续原决定", async () => {
    await openReview();
    const processing = { ...approval(), status: "processing" as const, reviewer_id: "reviewer", decision: { action: "approve" as const, proposal: null } };
    vi.mocked(api.getApproval).mockResolvedValue(processing);
    vi.mocked(api.decideApproval).mockImplementation((_id, _body, signal) => new Promise((_, reject) => {
      signal.addEventListener("abort", () => reject(new DOMException("cancel", "AbortError")), { once: true });
    }));
    await click("批准并加入看板");
    await click("停止等待");
    await vi.waitFor(() => expect(root.textContent).toContain("已提交的审批决定不会被撤销"));
    await vi.waitFor(() => expect(button("继续执行已保存的决定").disabled).toBe(false));
    expect(root.textContent).not.toContain("拒绝方案");
  });

  it.each(["reviewer", "another-reviewer"])("恢复只允许原审批人：%s", async reviewerId => {
    const value = approval();
    value.status = "processing"; value.reviewer_id = reviewerId;
    value.decision = { action: "reject", proposal: null };
    await openReview(value);
    if (reviewerId !== "reviewer") {
      expect(root.textContent).not.toContain("继续执行已保存的决定");
      expect(api.decideApproval).not.toHaveBeenCalled();
      return;
    }
    vi.mocked(api.decideApproval).mockResolvedValue({ ...value, status: "rejected" });
    await click("继续执行已保存的决定");
    expect(api.decideApproval).toHaveBeenCalledWith(value.id, value.decision, expect.any(AbortSignal), expect.any(Function));
  });
});

it("审批方案和原文中的 HTML 仅显示为文本", () => {
  const value = approval();
  const untrusted = '<img src=x onerror="window.injected=true">';
  value.plan.proposal.summary = untrusted;
  value.plan.sources = [{ source_id: 1, document_id: value.project_id, filename: "规则.md", chunk_index: 0, heading: "规则", text: untrusted }];
  mount(ApprovalDetails, { approval: value });
  expect(root.querySelectorAll("img, script, iframe")).toHaveLength(0);
  expect(root.querySelector("blockquote")?.textContent).toContain(untrusted);
});

it("执行轨迹合并同一步状态，并区分并行执行、失败和取消", async () => {
  const event = (id: string, status: TraceEvent["status"], name: TraceEvent["name"]): TraceEvent => ({
    version: 1, seq: 1, request_id: "test", type: "node", id, name, status,
  });
  const props = reactive({ events: [event("a", "started", "retrieve_documents"), event("b", "started", "load_task_board")], running: true });
  // 根组件 props 通过渲染函数保持响应式，模拟真实流式事件到达。
  const { h } = await import("vue");
  mount({ setup: () => () => h(RunTrace, props) });
  expect(root.querySelector("summary")?.textContent).toContain("检索需求文档、读取任务看板");
  props.events.push(event("a", "failed", "retrieve_documents")); props.running = false;
  await nextTick();
  expect(root.querySelectorAll("li")).toHaveLength(2);
  expect(root.textContent).toContain("失败"); expect(root.textContent).toContain("已停止");
  expect(root.textContent).not.toContain("进行中");
});
