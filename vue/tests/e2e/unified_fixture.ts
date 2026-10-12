import { randomUUID } from "node:crypto";
import { expect, type Page } from "@playwright/test";
import type { ApprovalVO, ChatAnswerVO, PlanDraftVO, PlanResultVO, SessionMessageQO, WorkflowResultVO } from "../../src/types/api";
import { ChatFixture } from "./chat_fixture";
import { finalResponse, savedDraft } from "./stream_helpers";

export const initialSummary = "先完成订单信息与库存校验，再联调下单流程。";
export const unsafeDescription = "收货人、手机号和配送地址为必填。<img src=x onerror=alert(1)>";
export const unsafeAssumption = "沿用现有登录流程。<script>window.planningInjected = true</script>";
export const sourceText = "创建订单必须填写收货人、手机号和配送地址。<img src=x onerror=alert(1)>\n" + "unbroken_document_excerpt_".repeat(12);
const timestamp = "2026-10-12T00:00:00Z";

export function planningResult(): PlanResultVO {
  return {
    mode: "mock", persisted: false, board_task_count: 3,
    proposal: {
      summary: initialSummary, assumptions: [unsafeAssumption],
      risks: ["并发下单可能造成库存超卖，需要原子扣减与回滚。"],
      tasks: [
        { draft_id: "T1", title: "实现订单收货信息", description: unsafeDescription, priority: 1,
          acceptance_criteria: "缺少收货人、手机号或地址时禁止提交。\n输入合法信息后可以进入订单确认页。", dependencies: [], source_ids: [1] },
        { draft_id: "T2", title: "校验库存与提交订单", description: "复用订单信息，在提交时检查可售库存。", priority: 2,
          acceptance_criteria: "库存不足时拒绝下单并显示明确原因。", dependencies: ["T1"], source_ids: [1] },
      ],
    },
    sources: [{ source_id: 1, document_id: randomUUID(), filename: "订单规则.md", chunk_index: 0, heading: "订单管理", text: sourceText }],
    tool_calls: [{ name: "search_documents", status: "success", item_count: 1 }, { name: "read_task_board", status: "success", item_count: 3 }],
  };
}

export function requirementResult(): WorkflowResultVO {
  const documentId = randomUUID(), taskId = randomUUID();
  return {
    intent: "requirement_check", mode: "live", status: "reviewed", persisted: false,
    answer: "已安排上传任务，删除文档可能缺少对应任务。",
    report: {
      summary: "已安排上传任务，删除文档可能缺少对应任务。", insufficient_evidence: false, reviewed_source_ids: [1],
      covered: [{ requirement: "上传文档", explanation: "已存在上传任务，仅表示已安排。", source_ids: [1], task_ids: [taskId] }],
      missing: [{ requirement: "删除文档", explanation: "当前任务未提到删除功能。<img src=x onerror=alert(1)>", source_ids: [1] }],
      questions: [{ question: "删除时是否清理索引？", reason: "已读片段未明确说明。", source_ids: [1] }],
    },
    tasks: [],
    sources: [{ source_id: 1, document_id: documentId, filename: "文档需求.md", chunk_index: 0, heading: "文档管理",
      text: "支持上传与删除文档。<script>window.injected=true</script>\n" + "long_unbroken_excerpt_".repeat(8) }],
    scope: {
      ready_documents: [{ document_id: documentId, filename: "文档需求.md" }], retrieved_source_count: 1,
      document_search_performed: true, full_document_review: false, board_read: true,
      tasks: [{ id: taskId, title: "实现文档上传", description: "上传 Markdown 和文本", acceptance_criteria: "上传成功后可查询状态",
        priority: 2, status: "in_progress", description_truncated: false, acceptance_criteria_truncated: false }],
      task_details_truncated: false, limitation: "仅按本次输入检索片段，未逐份检查全文。有对应任务不代表功能已经实现。",
    },
    tool_calls: [{ name: "search_documents", status: "success", item_count: 1 }, { name: "read_task_board", status: "success", item_count: 1 }],
  };
}

export function planAnswer(goal: string, plan: PlanResultVO, draft?: PlanDraftVO): ChatAnswerVO {
  return {
    mode: plan.mode, basis: "project", status: plan.mode === "mock" ? "demo" : "answered", answer: "已生成任务草案，请核对后提交。",
    sources: [], tasks: [], tool_calls: [{ name: "generate_task_plan", status: "success", item_count: plan.proposal.tasks.length }],
    artifacts: [{ type: "task_plan", goal, result: plan, draft_id: draft?.id ?? null, draft_version: draft?.version ?? null }],
  };
}

export function checkAnswer(result: WorkflowResultVO): ChatAnswerVO {
  return {
    mode: result.mode, basis: "project", status: result.status === "insufficient_evidence" ? "insufficient_evidence" : result.mode === "mock" ? "demo" : "answered",
    answer: "已保存需求检查报告，请展开核对。", sources: [], tasks: [],
    tool_calls: [{ name: "check_requirements", status: result.sources.length ? "success" : "empty", item_count: result.sources.length }],
    artifacts: [{ type: "requirement_check", result }],
  };
}

export async function setupUnified(page: Page, tab = "chat", initial: { mode?: "mock" | "live"; ready?: number; configured?: boolean } = {}) {
  const projectId = randomUUID(), fixture = new ChatFixture();
  const state = {
    projectId, fixture, mode: initial.mode ?? "mock", ready: initial.ready ?? 1, configured: initial.configured ?? true,
    plan: planningResult(), workflow: requirementResult(), result: (tab === "assistant" ? "check" : "plan") as "plan" | "check",
    answer: null as ChatAnswerVO | null, drafts: [] as PlanDraftVO[], approvals: [] as ApprovalVO[],
    calls: [] as { path: string; payload: SessionMessageQO }[], completed: 0,
    failure: 0, error: { code: "model_unavailable", message: "模型服务暂时不可用", request_id: "unified-test-request" },
    unexpected: [] as string[], gate: null as Promise<void> | null,
  };
  await page.addInitScript(() => sessionStorage.setItem("devpilot.access_token", "unified-regression-test"));
  await page.route("**/api/v1/**", async route => {
    const request = route.request(), path = new URL(request.url()).pathname, method = request.method();
    if (await fixture.handle(route)) return;
    if (path.endsWith("/me")) return route.fulfill({ json: { id: randomUUID(), username: "统一助手回归", role: "member" } });
    if (path === `/api/v1/projects/${projectId}`) return route.fulfill({ json: {
      id: projectId, name: "餐厅外卖网站", description: "在线点餐与订单管理", created_at: timestamp, updated_at: timestamp,
    } });
    if (path.endsWith("/chat") && method === "GET") return route.fulfill({ json: { mode: state.mode, configured: state.configured, ready_documents: state.ready } });
    if (/\/chat\/sessions\/[^/]+\/messages\/stream$/.test(path) && method === "POST") {
      const payload = request.postDataJSON() as SessionMessageQO;
      state.calls.push({ path, payload });
      const response = state.answer ? structuredClone(state.answer) : state.result === "check"
        ? checkAnswer(structuredClone(state.workflow)) : null;
      const plan = structuredClone(state.plan), failure = state.failure, error = structuredClone(state.error), gate = state.gate;
      state.gate = null;
      if (gate) await gate;
      try {
        if (request.failure()) return;
        if (failure) {
          const sessionId = path.split("/sessions/")[1]!.split("/")[0]!;
          const messages = fixture.messages.get(sessionId)!;
          const old = messages.find(item => item.client_message_id === payload.client_message_id);
          const failed = { id: old?.id ?? randomUUID(), client_message_id: payload.client_message_id, question: payload.question,
            intent: payload.intent ?? "auto", seq: old?.seq ?? messages.length + 1, answer: null, status: "failed" as const,
            error: error.message + "（请求编号：" + error.request_id + "）", created_at: timestamp };
          if (old) Object.assign(old, failed); else messages.push(failed);
          fixture.sessions.find(item => item.id === sessionId)!.title = payload.question;
          return await route.fulfill({ status: failure, json: { error } });
        }
        let answer = response;
        if (!answer) {
          plan.mode = state.mode;
          const draft = { ...savedDraft(projectId, payload.question, plan), id: randomUUID() } as PlanDraftVO;
          state.drafts.unshift(draft);
          answer = planAnswer(payload.question, draft.plan, draft);
        }
        fixture.record(path, payload, answer);
        const sessionId = path.split("/sessions/")[1]!.split("/")[0]!;
        fixture.messages.get(sessionId)!.find(item => item.client_message_id === payload.client_message_id)!.error = null;
        return await route.fulfill(finalResponse("chat", answer));
      } finally { state.completed++; }
    }
    const draftsPath = `/api/v1/projects/${projectId}/planning/drafts`;
    if (path === draftsPath && method === "GET") return route.fulfill({ json: { items: state.drafts, total: state.drafts.length, offset: 0, limit: 20 } });
    const draft = state.drafts.find(item => path.startsWith(`${draftsPath}/${item.id}`));
    if (draft && path.endsWith(draft.id)) {
      if (method === "GET") return route.fulfill({ json: draft });
      if (method === "PATCH") {
        const payload = request.postDataJSON();
        expect(payload.version).toBe(draft.version);
        draft.version++; draft.plan.proposal = payload.proposal;
        return route.fulfill({ json: draft });
      }
    }
    if (draft && path.endsWith("/submit/stream")) {
      expect(request.postDataJSON()).toEqual({ version: draft.version });
      const approval: ApprovalVO = {
        id: randomUUID(), conversation_id: randomUUID(), project_id: projectId, project_name: "餐厅外卖网站", goal: draft.goal,
        status: "pending", plan: draft.plan, decision: null, reviewer_id: null, created_tasks: [], created_at: timestamp, decided_at: null,
      };
      draft.status = "submitted"; draft.conversation_id = approval.conversation_id; state.approvals.unshift(approval);
      return route.fulfill(finalResponse("approval", approval));
    }
    if (path.endsWith("/conversations") && method === "GET") return route.fulfill({ json: state.approvals.map(approval => ({
      id: approval.conversation_id, project_id: projectId, goal: approval.goal, status: "pending", approval,
    })) });
    const approval = state.approvals.find(item => path.endsWith(`/approvals/${item.id}`));
    if (approval && method === "GET") return route.fulfill({ json: approval });
    state.unexpected.push(`${method} ${path}`);
    return route.fulfill({ status: 404, json: {} });
  });
  await page.goto(`/projects/${projectId}?tab=${tab}`);
  await expect(page.getByRole("button", { name: "刷新问答状态", exact: true })).toBeEnabled();
  return {
    state,
    hold() {
      let release!: () => void;
      state.gate = new Promise<void>(resolve => { release = resolve; });
      return release;
    },
  };
}

export async function sendQuestion(page: Page, question: string) {
  await page.getByLabel("你想了解什么？").fill(question);
  await page.getByRole("button", { name: "发送问题", exact: true }).click();
}
