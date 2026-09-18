import { randomUUID } from "node:crypto";
import { test, expect, type Page } from "@playwright/test";
import type { WorkflowResultVO } from "../../src/types/api";

async function setup(page: Page) {
  const project = randomUUID(),
    taskId = randomUUID(),
    docId = randomUUID();
  const task = {
    id: taskId,
    title: "实现文档上传",
    description: "上传 Markdown 和文本",
    acceptance_criteria: "上传成功后可查询状态",
    priority: 2,
    status: "in_progress" as const,
    description_truncated: false,
    acceptance_criteria_truncated: false,
  };
  const result: WorkflowResultVO = {
    intent: "requirement_check",
    mode: "live",
    status: "reviewed",
    persisted: false,
    answer: "已安排上传任务，删除文档可能缺少对应任务。",
    report: {
      summary: "已安排上传任务，删除文档可能缺少对应任务。",
      insufficient_evidence: false,
      reviewed_source_ids: [1],
      covered: [
        {
          requirement: "上传文档",
          explanation: "已存在上传任务，仅表示已安排。",
          source_ids: [1],
          task_ids: [taskId],
        },
      ],
      missing: [
        {
          requirement: "删除文档",
          explanation: "当前任务未提到删除功能。<img src=x onerror=alert(1)>",
          source_ids: [1],
        },
      ],
      questions: [
        {
          question: "删除时是否清理索引？",
          reason: "已读片段未明确说明。",
          source_ids: [1],
        },
      ],
    },
    tasks: [],
    sources: [
      {
        source_id: 1,
        document_id: docId,
        filename: "文档需求.md",
        chunk_index: 0,
        heading: "文档管理",
        text:
          "支持上传与删除文档。<script>window.injected=true</script>\n" +
          "long_unbroken_excerpt_".repeat(8),
      },
    ],
    scope: {
      ready_documents: [{ document_id: docId, filename: "文档需求.md" }],
      retrieved_source_count: 1,
      document_search_performed: true,
      full_document_review: false,
      board_read: true,
      tasks: [task],
      task_details_truncated: false,
      limitation:
        "仅按本次输入检索片段，未逐份检查全文。有对应任务不代表功能已经实现。",
    },
    tool_calls: [
      { name: "search_documents", status: "success", item_count: 1 },
      { name: "read_task_board", status: "success", item_count: 1 },
    ],
  };
  const state = {
    result,
    mode: "live",
    ready: 1,
    configured: true,
    failure: 0,
    calls: [] as unknown[],
    unexpected: [] as string[],
    gate: null as Promise<void> | null,
    completed: 0,
  };
  await page.addInitScript(() =>
    sessionStorage.setItem("devpilot.access_token", "offline-test-token"),
  );
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request(),
      path = new URL(request.url()).pathname;
    if (request.method() === "GET" && path.endsWith("/me"))
      return route.fulfill({
        json: { id: randomUUID(), username: "需求检查测试", role: "member" },
      });
    if (request.method() === "GET" && path === `/api/v1/projects/${project}`)
      return route.fulfill({
        json: {
          id: project,
          name: "文档协作项目",
          description: "上传与管理资料",
          created_at: "2026-09-16T00:00:00Z",
          updated_at: "2026-09-16T00:00:00Z",
        },
      });
    if (request.method() === "GET" && path.endsWith("/assistant"))
      return route.fulfill({
        json: {
          mode: state.mode,
          ready_documents: state.ready,
          configured: state.configured,
          task_count: 1,
        },
      });
    if (request.method() === "POST" && path.endsWith("/assistant/runs")) {
      state.calls.push(request.postDataJSON());
      const response = structuredClone(state.result),
        failure = state.failure,
        gate = state.gate;
      state.gate = null;
      if (gate) await gate;
      try {
        return await route.fulfill(
          failure
            ? {
                status: failure,
                json: {
                  error: {
                    code: "workflow_context_changed",
                    message: "检查期间任务发生变化，请重新检查",
                    request_id: "workflow-test-id",
                  },
                },
              }
            : { json: response },
        );
      } finally {
        state.completed++;
      }
    }
    state.unexpected.push(`${request.method()} ${path}`);
    return route.fulfill({ status: 404, json: {} });
  });
  await page.goto(`/projects/${project}?tab=assistant`);
  await expect(
    page.getByRole("button", { name: "开始检查", exact: true }),
  ).toBeEnabled();
  return {
    state,
    project,
    task,
    hold() {
      let release!: () => void;
      state.gate = new Promise<void>((resolve) => {
        release = resolve;
      });
      return release;
    },
  };
}

test("需求检查展示三类发现、对应任务、真实范围，内容安全且双端可读", async ({
  page,
}) => {
  const { state } = await setup(page);
  await expect(
    page
      .getByRole("navigation", { name: "项目功能" })
      .getByRole("link", { name: "需求检查", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await page.getByRole("button", { name: "开始检查", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "已有对应任务", exact: true }),
  ).toContainText("实现文档上传 · 进行中");
  await expect(
    page.getByRole("region", { name: "可能遗漏", exact: true }),
  ).toContainText("删除文档");
  await expect(
    page.getByRole("region", { name: "需要确认", exact: true }),
  ).toContainText("删除时是否清理索引");
  const scope = page.getByRole("region", { name: "依据与检查范围" });
  await expect(scope).toContainText("未逐份检查全文");
  await expect(scope).toContainText("1 个片段");
  await expect(scope).toContainText("<script>window.injected=true</script>");
  await page
    .getByRole("region", { name: "可能遗漏", exact: true })
    .getByRole("link", { name: "依据 [1]", exact: true })
    .click();
  await expect(page.locator("#check-source-1")).toBeInViewport();
  await page.getByText("本次读取的看板任务（1 项）", { exact: true }).click();
  await expect(scope).toContainText("上传成功后可查询状态");
  await expect(
    page
      .getByRole("region", { name: "项目需求检查", exact: true })
      .locator("img, script, iframe"),
  ).toHaveCount(0);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/screenshots/requirement-check-desktop.png",
    fullPage: true,
    animations: "disabled",
  });
  for (const width of [390, 360, 768]) {
    await page.setViewportSize({ width, height: 844 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
    await expect(
      page.getByRole("link", { name: "需求检查", exact: true }),
    ).toBeVisible();
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/screenshots/requirement-check-mobile.png",
    fullPage: true,
    animations: "disabled",
  });
  expect(state.calls).toEqual([
    {
      message: "对照需求文档，看看现有任务还漏了什么，有哪些需求需要确认？",
      intent: "auto",
    },
  ]);
  expect(state.unexpected).toEqual([]);
});

test("没有遗漏允许空建议，资料不足和演示结果不能冒充检查完成", async ({
  page,
}) => {
  const { state } = await setup(page);
  state.result.report!.missing = [];
  await page.getByRole("button", { name: "开始检查", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "可能遗漏", exact: true }),
  ).toContainText("在本次已读片段中未发现明显遗漏");
  state.result.status = "insufficient_evidence";
  state.result.report = null;
  state.result.answer = "没有检索到可用于对照的需求片段，无法判断是否遗漏。";
  await page.getByRole("button", { name: "开始检查", exact: true }).click();
  await expect(
    page.getByText("资料不足不等于没有遗漏。", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "可能遗漏", exact: true }),
  ).toHaveCount(0);
  state.result.status = "demo";
  state.result.mode = "mock";
  state.result.answer = "演示模式未调用聊天模型，不判断需求覆盖或遗漏。";
  state.mode = "mock";
  await page.getByRole("button", { name: "刷新检查状态" }).click();
  await page.getByRole("button", { name: "开始检查", exact: true }).click();
  await expect(
    page.getByText(state.result.answer, { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "可能遗漏", exact: true }),
  ).toHaveCount(0);
});

test("取消等待并忽略迟到结果，重新提交和离开页面清空报告", async ({ page }) => {
  const { state, hold } = await setup(page);
  const release = hold();
  await page.getByRole("button", { name: "开始检查", exact: true }).click();
  await expect.poll(() => state.calls.length).toBe(1);
  await page.getByRole("button", { name: "取消等待" }).click();
  await expect(page.getByRole("alert")).toContainText("已取消等待");
  state.result.answer = "第二次检查结果";
  await page.getByRole("button", { name: "开始检查", exact: true }).click();
  await expect(page.getByText("第二次检查结果", { exact: true })).toBeVisible();
  release();
  await expect.poll(() => state.completed).toBe(2);
  await expect(page.getByText("第二次检查结果", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "项目概览", exact: true }).click();
  await page.getByRole("link", { name: "需求检查", exact: true }).click();
  await expect(page.getByText("第二次检查结果", { exact: true })).toHaveCount(
    0,
  );
  expect(state.unexpected).toEqual([]);
});

test("变更冲突保留输入可重试，清空后不显示旧结果", async ({ page }) => {
  const { state } = await setup(page);
  state.failure = 409;
  await page
    .getByLabel("检查范围或问题", { exact: true })
    .fill("只检查文档删除需求");
  await page.getByRole("button", { name: "开始检查", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("workflow-test-id");
  await expect(page.getByLabel("检查范围或问题", { exact: true })).toHaveValue(
    "只检查文档删除需求",
  );
  state.failure = 0;
  await page.getByRole("button", { name: "开始检查", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "可能遗漏", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "清空结果", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "可能遗漏", exact: true }),
  ).toHaveCount(0);
});

test("无文档也能查询任务，手动用途可纠正自动分类", async ({ page }) => {
  const { state, task } = await setup(page);
  state.ready = 0;
  state.result.intent = "task_lookup";
  state.result.status = "answered";
  state.result.report = null;
  state.result.tasks = [task];
  state.result.sources = [];
  state.result.scope.document_search_performed = false;
  state.result.answer = "找到一项进行中任务";
  await page.getByRole("button", { name: "刷新检查状态" }).click();
  await page
    .getByRole("button", { name: "查看进行中任务", exact: true })
    .click();
  await page.getByRole("button", { name: "开始检查", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "查询到的任务" }),
  ).toContainText("实现文档上传");
  expect(state.calls[0]).toEqual({
    message: "看板中有哪些进行中的任务？",
    intent: "task_lookup",
  });
  state.result.intent = "knowledge_question";
  state.result.answer = "原文中的验收规则 [1]";
  state.result.tasks = [];
  await page.getByRole("button", { name: "询问文档规则", exact: true }).click();
  await page.getByRole("button", { name: "开始检查", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "文档问答", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("原文中的验收规则 [1]", { exact: true }),
  ).toBeVisible();
  expect(state.unexpected).toEqual([]);
});

test("空输入不能提交，未配置模型时提示且禁用请求", async ({ page }) => {
  const { state } = await setup(page);
  await page.getByLabel("检查范围或问题", { exact: true }).fill("   ");
  await page.getByRole("button", { name: "开始检查", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("请输入 1～2000");
  expect(state.calls).toHaveLength(0);
  state.configured = false;
  await page.getByRole("button", { name: "刷新检查状态" }).click();
  await expect(
    page.getByRole("button", { name: "开始检查", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText("真实模式尚未配置模型，请联系部署维护者完成配置后刷新。", {
      exact: true,
    }),
  ).toBeVisible();
});
