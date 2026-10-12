import { randomUUID } from "node:crypto";
import { expect, test, type Page } from "@playwright/test";
import { ChatFixture } from "./chat_fixture";
import { finalResponse, savedDraft } from "./stream_helpers";
import type {
  ApprovalVO,
  ChatAnswerVO,
  PlanDraftVO,
  PlanProposalVO,
  PlanResultVO,
  SessionMessageQO,
  WorkflowResultVO,
} from "../../src/types/api";

const timestamp = "2026-10-12T00:00:00Z";

async function assistant(page: Page) {
  const projectId = randomUUID(), documentId = randomUUID(), taskId = randomUUID();
  const fixture = new ChatFixture();
  const source = {
    source_id: 1, document_id: documentId, filename: "文档管理需求.md", chunk_index: 0,
    heading: "文档管理", text: "支持上传和删除文档。<script>window.injected=true</script>",
  };
  const task = {
    id: taskId, title: "实现文档上传", status: "in_progress" as const, priority: 2,
    description: "支持 Markdown 和文本上传", acceptance_criteria: "上传成功后可以检索资料",
    description_truncated: false, acceptance_criteria_truncated: false,
  };
  const plan: PlanResultVO = {
    mode: "live", persisted: true, board_task_count: 1,
    proposal: {
      summary: "补齐文档删除和索引清理流程。",
      assumptions: ["先确认删除权限"], risks: ["删除文档后需要清理索引"],
      tasks: [{ draft_id: "T1", title: "实现文档删除", description: "删除文档并清理检索索引",
        acceptance_criteria: "删除后文档和检索片段均不可访问", priority: 2, dependencies: [], source_ids: [1] }],
    },
    sources: [source], tool_calls: [{ name: "search_documents", status: "success", item_count: 1 },
      { name: "read_task_board", status: "success", item_count: 1 }],
  };
  const report: WorkflowResultVO = {
    intent: "requirement_check", mode: "live", status: "reviewed", persisted: false,
    answer: "上传已有任务，删除流程可能遗漏，索引清理规则需要确认。",
    report: {
      summary: "文档管理检查摘要", insufficient_evidence: false, reviewed_source_ids: [1],
      covered: [{ requirement: "上传文档", explanation: "已安排上传任务。", source_ids: [1], task_ids: [taskId] }],
      missing: [{ requirement: "删除文档", explanation: "任务中没有删除流程。<img src=x onerror=alert(1)>", source_ids: [1] }],
      questions: [{ question: "删除时是否同步清理索引？", reason: "已读片段未明确清理规则。", source_ids: [1] }],
    },
    tasks: [], sources: [source], tool_calls: plan.tool_calls,
    scope: {
      ready_documents: [{ document_id: documentId, filename: source.filename }], retrieved_source_count: 1,
      document_search_performed: true, full_document_review: false, board_read: true, tasks: [task],
      task_details_truncated: false, limitation: "仅检索本次相关片段，未逐份检查全文；有任务不代表功能已完成。",
    },
  };
  const draft = savedDraft(projectId, "完善文档管理", plan) as PlanDraftVO;
  const approval: ApprovalVO = {
    id: randomUUID(), conversation_id: randomUUID(), project_id: projectId, project_name: "统一助手项目",
    goal: draft.goal, status: "pending", plan, decision: null, reviewer_id: null,
    created_tasks: [], created_at: timestamp, decided_at: null,
  };
  const state = {
    projectId, fixture, draft, approval, report,
    result: "plan" as "plan" | "check" | "text", text: "可以继续核对项目资料。", failNext: false,
    calls: [] as { sessionId: string; payload: SessionMessageQO }[],
    draftReads: 0, patches: [] as { version: number; proposal: PlanProposalVO }[],
    draftHold: null as Promise<void> | null,
    submissions: [] as { version: number }[], legacyCalls: [] as string[], unexpected: [] as string[],
  };
  await page.addInitScript(() => sessionStorage.setItem("devpilot.access_token", "unified-assistant-test"));
  await page.route("**/api/v1/**", async route => {
    const request = route.request(), url = new URL(request.url()), path = url.pathname, method = request.method();
    if (path.endsWith("/me")) return route.fulfill({ json: {
      id: randomUUID(), username: "统一助手成员", role: "member", created_at: timestamp, updated_at: timestamp,
    } });
    if (path === `/api/v1/projects/${projectId}`) return route.fulfill({ json: {
      id: projectId, owner_id: randomUUID(), name: "统一助手项目", description: "文档管理",
      created_at: timestamp, updated_at: timestamp,
    } });
    if (path.endsWith("/chat")) return route.fulfill({ json: { mode: "live", configured: true, ready_documents: 1 } });
    if (await fixture.handle(route)) return;
    if (/\/chat\/sessions\/[^/]+\/messages\/stream$/.test(path)) {
      const payload = request.postDataJSON() as SessionMessageQO;
      expect(payload).toEqual({ question: expect.any(String), intent: expect.any(String), client_message_id: expect.any(String) });
      const sessionId = path.split("/sessions/")[1]!.split("/")[0]!;
      state.calls.push({ sessionId, payload });
      if (state.failNext) {
        state.failNext = false;
        return route.fulfill({ status: 502, json: { error: { code: "model_unavailable", message: "模型暂时不可用" } } });
      }
      let answer: ChatAnswerVO;
      if (state.result === "plan") {
        state.draft.goal = payload.question;
        answer = {
          mode: "live", basis: "project", status: "answered", answer: "已保存任务草案，请核对后提交。",
          sources: [], tasks: [], tool_calls: [{ name: "generate_task_plan", status: "success", item_count: 1 }],
          artifacts: [{ type: "task_plan", goal: payload.question, result: structuredClone(state.draft.plan),
            draft_id: state.draft.id, draft_version: 1 }],
        };
      } else if (state.result === "check") answer = {
        mode: "live", basis: "project", status: "answered", answer: "已保存需求检查报告。",
        sources: [], tasks: [], tool_calls: [{ name: "check_requirements", status: "success", item_count: 1 }],
        artifacts: [{ type: "requirement_check", result: structuredClone(state.report) }],
      };
      else answer = { mode: "live", basis: "general", status: "answered", answer: state.text,
        sources: [], tasks: [], tool_calls: [], artifacts: [] };
      fixture.record(path, payload, answer);
      return route.fulfill(finalResponse("chat", answer));
    }
    const draftsPath = `/api/v1/projects/${projectId}/planning/drafts`;
    if (path === draftsPath && method === "GET") return route.fulfill({ json: {
      items: [state.draft], total: 1, offset: 0, limit: 20,
    } });
    if (path === `${draftsPath}/${state.draft.id}`) {
      if (method === "GET") { state.draftReads++; if (state.draftHold) await state.draftHold; return route.fulfill({ json: state.draft }); }
      if (method === "PATCH") {
        const payload = request.postDataJSON();
        expect(payload.version).toBe(state.draft.version);
        state.patches.push(payload);
        state.draft = { ...state.draft, version: state.draft.version + 1,
          plan: { ...state.draft.plan, proposal: payload.proposal } };
        return route.fulfill({ json: state.draft });
      }
    }
    if (path === `${draftsPath}/${state.draft.id}/submit/stream`) {
      const payload = request.postDataJSON();
      expect(payload).toEqual({ version: state.draft.version });
      state.submissions.push(payload);
      state.approval = { ...state.approval, goal: state.draft.goal, plan: structuredClone(state.draft.plan) };
      state.draft = { ...state.draft, status: "submitted", conversation_id: state.approval.conversation_id };
      return route.fulfill(finalResponse("approval", state.approval));
    }
    if (path === `/api/v1/approvals/${state.approval.id}` && method === "GET") return route.fulfill({ json: state.approval });
    if (path === `/api/v1/conversations/${state.approval.conversation_id}` && method === "GET") return route.fulfill({ json: {
      id: state.approval.conversation_id, project_id: projectId, goal: state.draft.goal, status: state.approval.status, approval: state.approval,
    } });
    if (path === `/api/v1/projects/${projectId}/conversations` && method === "GET") return route.fulfill({ json:
      state.draft.status === "submitted" ? [{ id: state.approval.conversation_id, project_id: projectId,
        goal: state.draft.goal, status: "pending", approval: state.approval }] : [],
    });
    if (method !== "GET" && (/\/planning\/(?:drafts\/)?stream$|\/workflow\/stream$|\/conversations$|\/runs\/stream$|\/decide\/stream$/.test(path))) {
      state.legacyCalls.push(`${method} ${path}`);
      return route.fulfill({ status: 400, json: { error: { code: "unexpected_mutation", message: "统一助手不应调用旧生成或审批决定接口" } } });
    }
    state.unexpected.push(`${method} ${path}`);
    return route.fulfill({ status: 404, json: {} });
  });
  await page.goto(`/projects/${projectId}?tab=chat`);
  await page.getByRole("region", { name: "项目聊天助手", exact: true }).waitFor();
  await expect(page.getByLabel("你想了解什么？")).toBeEnabled();
  return state;
}

async function send(page: Page, question: string) {
  await page.getByLabel("你想了解什么？").fill(question);
  await page.getByRole("button", { name: "发送问题", exact: true }).click();
}

test("自动生成的草案随消息恢复，375px详情堆叠且关闭后能继续聊天", async ({ page }) => {
  const state = await assistant(page);
  await expect(page.getByRole("button", { name: "自动处理", exact: true })).toHaveAttribute("aria-pressed", "true");
  await send(page, "完善文档管理并生成任务草案");
  const detail = page.getByLabel("结果详情", { exact: true });
  const card = page.getByRole("button", { name: "打开任务草案", exact: true });
  await expect(detail).toContainText("已保存 · 第 1 版");
  expect(state.calls[0]!.payload.intent).toBe("auto");
  const sessionId = state.calls[0]!.sessionId;
  await page.getByRole("button", { name: "关闭结果详情", exact: true }).click();
  await expect(detail).toHaveCount(0);
  await expect(card).toContainText("已保存");
  await page.reload();
  await expect(card).toBeVisible();
  await card.click();
  await expect(detail).toContainText("补齐文档删除和索引清理流程。");
  expect(state.calls).toHaveLength(1);
  expect(state.draftReads).toBeGreaterThanOrEqual(2);
  expect(new URL(page.url()).searchParams.get("chat_session")).toBe(sessionId);
  await page.screenshot({ path: "test-results/screenshots/unified-assistant-desktop.png", fullPage: true });

  await page.setViewportSize({ width: 375, height: 812 });
  const panel = page.getByRole("region", { name: "项目聊天助手", exact: true });
  await expect.poll(() => panel.evaluate(element => getComputedStyle(element).gridTemplateColumns.split(" ").length)).toBe(1);
  const conversation = await panel.locator(":scope > div").first().boundingBox();
  const result = await detail.boundingBox();
  expect(conversation!.y + conversation!.height).toBeLessThanOrEqual(result!.y + 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: "test-results/screenshots/unified-assistant-mobile.png", fullPage: true });
  await page.getByRole("button", { name: "关闭结果详情", exact: true }).click();
  state.result = "text";
  await send(page, "继续解释删除权限");
  await expect(page.getByText(state.text, { exact: true })).toBeVisible();
  expect(state.calls[1]!.sessionId).toBe(sessionId);
  expect(state.legacyCalls).toEqual([]);
  expect(state.unexpected).toEqual([]);
});

test("恢复中的消息继续轮询，等待草案详情不会阻塞后台结果", async ({ page }) => {
  const state = await assistant(page);
  await send(page, "先保存文档管理草案");
  await expect(page.getByLabel("结果详情", { exact: true })).toContainText("已保存 · 第 1 版");
  await page.getByRole("button", { name: "关闭结果详情", exact: true }).click();
  const sessionId = state.calls[0]!.sessionId;
  const messages = state.fixture.messages.get(sessionId)!;
  messages.push({ id: randomUUID(), client_message_id: randomUUID(), seq: 2, question: "后台正在处理的问题", intent: "auto", answer: null, status: "pending", error: null, created_at: timestamp });
  await page.reload();
  await expect(page.getByText("服务端正在处理，完成后会自动更新。", { exact: true })).toBeVisible();
  let releaseDraft!: () => void;
  state.draftHold = new Promise<void>(resolve => { releaseDraft = resolve; });
  try {
    await page.getByRole("button", { name: "打开任务草案", exact: true }).click();
    await expect(page.getByText("正在读取最新草案状态……", { exact: true })).toBeVisible();
    messages[1]!.answer = { mode: "live", basis: "general", status: "answered", answer: "后台计算已完成，消息恢复成功。", sources: [], tasks: [], tool_calls: [], artifacts: [] };
    messages[1]!.status = "completed";
    await expect(page.getByText("后台计算已完成，消息恢复成功。", { exact: true })).toBeVisible({ timeout: 7000 });
  } finally { state.draftHold = null; releaseDraft(); }
  await expect(page.getByLabel("你想了解什么？")).toBeEnabled();
  expect(state.calls).toHaveLength(1);
});

test("显式规划和检查请求失败后，重试保留原用途和幂等编号", async ({ page }) => {
  const state = await assistant(page);
  state.result = "text";
  for (const [label, intent] of [["生成任务草案", "task_planning"], ["检查需求缺口", "requirement_check"]] as const) {
    await page.getByRole("button", { name: label, exact: true }).click();
    state.failNext = true;
    const before = state.calls.length;
    await send(page, `请${label}`);
    await expect(page.getByRole("alert")).toContainText("模型暂时不可用");
    await page.getByRole("button", { name: "自动处理", exact: true }).click();
    state.text = `${label}重试完成`;
    await page.getByRole("button", { name: "重试此问题", exact: true }).click();
    await expect(page.getByText(state.text, { exact: true })).toBeVisible();
    const first = state.calls[before]!, retry = state.calls[before + 1]!;
    expect(first.payload.intent).toBe(intent);
    expect(retry.payload).toEqual(first.payload);
    expect(retry.sessionId).toBe(first.sessionId);
  }
  expect(state.calls).toHaveLength(4);
  expect(state.fixture.messages.get(state.calls[0]!.sessionId)).toHaveLength(2);
  expect(state.legacyCalls).toEqual([]);
  expect(state.unexpected).toEqual([]);
});

test("需求报告保留覆盖与依据，按缺口只填规划目标，发送时沿用原会话", async ({ page }) => {
  const state = await assistant(page);
  state.result = "check";
  await page.getByRole("button", { name: "检查需求缺口", exact: true }).click();
  await send(page, "检查文档管理需求还有哪些遗漏");
  const detail = page.getByLabel("结果详情", { exact: true });
  await expect(detail).toContainText(state.report.answer);
  await expect(detail.getByRole("region", { name: "已有对应任务", exact: true })).toContainText("实现文档上传 · 进行中");
  await expect(detail.getByRole("region", { name: "可能遗漏", exact: true })).toContainText("删除文档");
  await expect(detail.getByRole("region", { name: "需要确认", exact: true })).toContainText("删除时是否同步清理索引？");
  const scope = detail.getByRole("region", { name: "依据与检查范围", exact: true });
  await expect(scope).toContainText(state.report.scope.limitation);
  await expect(scope).toContainText("已读取 1 项任务");
  await expect(scope).toContainText("<script>window.injected=true</script>");
  await expect(detail.locator("script,img,iframe")).toHaveCount(0);
  const citation = detail.getByRole("region", { name: "可能遗漏", exact: true }).getByRole("link", { name: "依据 [1]", exact: true });
  const href = await citation.getAttribute("href");
  expect(href).toMatch(/^#check-source-chat-artifact-/);
  await expect(detail.locator(`[id="${href!.slice(1)}"]`)).toContainText("文档管理需求.md");

  const savedAnswer = state.report.answer;
  state.report.answer = "后续检查才会返回的新报告，不能覆盖已保存的消息快照。";
  await page.getByRole("button", { name: "关闭结果详情", exact: true }).click();
  await expect(detail).toHaveCount(0);
  await page.reload();
  await page.getByRole("button", { name: "打开需求检查报告", exact: true }).click();
  await expect(detail).toContainText(savedAnswer);
  await expect(detail).not.toContainText(state.report.answer);
  expect(state.calls).toHaveLength(1);

  const sessionId = state.calls[0]!.sessionId;
  await detail.getByRole("button", { name: "按缺口生成草案", exact: true }).click();
  const input = page.getByLabel("你想了解什么？");
  await expect(input).toHaveValue(/删除文档/);
  const goal = await input.inputValue();
  expect(goal.length).toBeLessThanOrEqual(2000);
  expect(goal).not.toContain("[1]");
  await expect(page.getByRole("button", { name: "生成任务草案", exact: true })).toHaveAttribute("aria-pressed", "true");
  expect(state.calls).toHaveLength(1);
  expect(state.fixture.sessions).toHaveLength(1);
  state.result = "plan";
  await page.getByRole("button", { name: "发送问题", exact: true }).click();
  await expect(detail).toContainText("已保存 · 第 1 版");
  expect(state.calls[1]!.payload).toMatchObject({ question: goal, intent: "task_planning" });
  expect(state.calls[1]!.sessionId).toBe(sessionId);
  expect(state.calls[1]!.payload.client_message_id).not.toBe(state.calls[0]!.payload.client_message_id);
  expect(state.fixture.sessions).toHaveLength(1);
  expect(state.legacyCalls).toEqual([]);
  expect(state.unexpected).toEqual([]);
});

test("草案读取最新版本，修改后用保存版本送审，成员仅查看审批状态", async ({ page }) => {
  const state = await assistant(page);
  state.draft.version = 3;
  await page.getByRole("button", { name: "生成任务草案", exact: true }).click();
  await send(page, "完善文档删除流程");
  const detail = page.getByLabel("结果详情", { exact: true });
  await expect(detail).toContainText("已保存 · 第 3 版");
  expect(state.draftReads).toBeGreaterThanOrEqual(1);
  await detail.getByRole("button", { name: "编辑草案", exact: true }).click();
  await detail.getByLabel("任务标题", { exact: true }).fill("实现文档删除与索引清理");
  await expect(page.getByRole("button", { name: "关闭结果详情", exact: true })).toBeDisabled();
  await detail.getByRole("button", { name: "保存修改", exact: true }).click();
  await expect(detail).toContainText("已保存 · 第 4 版");
  expect(state.patches).toHaveLength(1);
  expect(state.patches[0]!.version).toBe(3);
  expect(state.patches[0]!.proposal.tasks[0]!.title).toBe("实现文档删除与索引清理");
  await detail.getByRole("button", { name: "提交这一版", exact: true }).click();
  await expect(detail.getByRole("status")).toContainText("等待审批");
  await expect(detail).toContainText("已保存 · 第 4 版 · 已提交审批");
  await expect(page.getByRole("button", { name: "打开任务草案", exact: true })).toContainText("第 4 版 · 已提交审批");
  expect(state.submissions).toEqual([{ version: 4 }]);
  expect(state.approval.plan.proposal.tasks[0]!.title).toBe("实现文档删除与索引清理");
  expect(state.approval.created_tasks).toEqual([]);
  await expect(detail.getByRole("button", { name: /批准|拒绝/ })).toHaveCount(0);
  expect(state.calls).toHaveLength(1);
  expect(state.legacyCalls).toEqual([]);
  expect(state.unexpected).toEqual([]);
});

test("旧规划和检查链接打开同一项目助手，预选用途并保留会话与工件query", async ({ page }) => {
  const state = await assistant(page);
  const sessionId = randomUUID();
  state.fixture.sessions.push({ id: sessionId, title: "已有会话", created_at: timestamp, updated_at: timestamp });
  state.fixture.messages.set(sessionId, []);
  const oldAnswer: ChatAnswerVO = { mode: "live", basis: "general", status: "answered",
    answer: "旧聊天记录仍可阅读。", sources: [], tasks: [], tool_calls: [] };
  state.fixture.record(`/api/v1/projects/${state.projectId}/chat/sessions/${sessionId}/messages/stream`,
    { question: "已有问题", client_message_id: randomUUID(), intent: "auto" }, oldAnswer);
  const planningQuery = new URLSearchParams({ tab: "planning", chat_session: sessionId,
    draft: state.draft.id, approval: state.approval.id });
  await page.goto(`/projects/${state.projectId}?${planningQuery}`);
  await expect(page.getByRole("link", { name: "项目助手", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("button", { name: "生成任务草案", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText(oldAnswer.answer, { exact: true })).toBeVisible();
  await expect(page.getByLabel("结果详情", { exact: true })).toContainText("已保存 · 第 1 版");
  const input = page.getByLabel("你想了解什么？");
  await input.fill("切换别名时保留本次草稿");
  await page.getByRole("link", { name: "项目助手", exact: true }).click();
  await expect(input).toHaveValue("切换别名时保留本次草稿");
  const normalized = new URL(page.url()).searchParams;
  expect(normalized.get("tab")).toBe("chat");
  expect(normalized.get("chat_session")).toBe(sessionId);
  expect(normalized.get("draft")).toBe(state.draft.id);
  expect(normalized.get("approval")).toBe(state.approval.id);

  const checkQuery = new URLSearchParams({ tab: "assistant", chat_session: sessionId, approval: state.approval.id });
  await page.goto(`/projects/${state.projectId}?${checkQuery}`);
  await expect(page.getByRole("link", { name: "项目助手", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("button", { name: "检查需求缺口", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByLabel("结果详情", { exact: true })).toContainText("等待审批");
  const restored = new URL(page.url()).searchParams;
  expect(restored.get("tab")).toBe("assistant");
  expect(restored.get("chat_session")).toBe(sessionId);
  expect(restored.get("approval")).toBe(state.approval.id);
  expect(state.calls).toHaveLength(0);
  expect(state.legacyCalls).toEqual([]);
  expect(state.unexpected).toEqual([]);
});

test("草案与审批抽屉直接打开最新草案并查看送审记录，全程不创建聊天会话", async ({ page }) => {
  const state = await assistant(page);
  const drawer = page.getByRole("dialog", { name: "草案与审批记录", exact: true });
  await page.getByRole("button", { name: "草案与审批", exact: true }).click();
  const saved = drawer.getByRole("region", { name: "已保存草案", exact: true });
  const open = saved.getByRole("button", { name: `打开草案：${state.draft.goal}`, exact: true });
  await expect(open).toContainText("待提交 · 第 1 版");
  // 列表显示的是旧版本，打开时应通过 getDraft 读取服务器的最新版本。
  state.draft = { ...state.draft, version: 5, plan: { ...state.draft.plan,
    proposal: { ...state.draft.plan.proposal, summary: "第五版已确认删除权限和索引清理范围。" } } };
  await open.click();
  await expect(drawer).toHaveCount(0);
  const detail = page.getByLabel("结果详情", { exact: true });
  await expect(detail).toContainText("已保存 · 第 5 版");
  await expect(detail).toContainText("第五版已确认删除权限和索引清理范围。");
  expect(state.draftReads).toBeGreaterThanOrEqual(1);
  expect(state.calls).toHaveLength(0);
  expect(state.fixture.sessions).toHaveLength(0);
  expect(new URL(page.url()).searchParams.has("chat_session")).toBe(false);

  await detail.getByRole("button", { name: "提交这一版", exact: true }).click();
  await expect(detail.getByRole("status")).toHaveText("等待审批");
  expect(state.submissions).toEqual([{ version: 5 }]);
  await page.getByRole("button", { name: "草案与审批", exact: true }).click();
  await drawer.getByRole("button", { name: "审批记录", exact: true }).click();
  const records = drawer.getByRole("region", { name: "持久规划与审批", exact: true });
  const record = records.getByRole("list", { name: "规划记录", exact: true }).getByRole("listitem");
  await expect(record).toHaveCount(1);
  await expect(record).toContainText(state.draft.goal);
  await expect(record).toContainText("等待审批");
  await record.getByRole("button", { name: "查看方案", exact: true }).click();
  const approval = records.getByRole("region", { name: "审批方案详情", exact: true });
  await expect(approval.getByRole("status")).toHaveText("等待审批");
  await expect(approval).toContainText("第五版已确认删除权限和索引清理范围。");
  await expect(drawer.getByRole("button", { name: /批准|拒绝|继续处理/ })).toHaveCount(0);
  expect(state.calls).toHaveLength(0);
  expect(state.fixture.sessions).toHaveLength(0);
  expect(state.approval.created_tasks).toEqual([]);
  expect(new URL(page.url()).searchParams.has("chat_session")).toBe(false);
  expect(state.legacyCalls).toEqual([]);
  expect(state.unexpected).toEqual([]);
});
