import { finalResponse, savedDraft } from "./stream_helpers";
import { randomUUID } from "node:crypto";
import { test, expect, type Page } from "@playwright/test";

const initialSummary = "先完成订单信息与库存校验，再联调下单流程。";
const unsafeDescription =
  "收货人、手机号和配送地址为必填。<img src=x onerror=alert(1)>";
const unsafeAssumption =
  "沿用现有登录流程。<script>window.planningInjected = true</script>";
const sourceText =
  "创建订单必须填写收货人、手机号和配送地址。<img src=x onerror=alert(1)>\n" +
  "unbroken_document_excerpt_".repeat(12);

async function planning(
  page: Page,
  initial: {
    mode?: "mock" | "live";
    configured?: boolean;
    ready?: number;
  } = {},
) {
  const id = randomUUID();
  const drafts: ReturnType<typeof savedDraft>[] = [];
  const state = {
    mode: "mock" as "mock" | "live",
    configured: true,
    ready: 1,
    fail: false,
    summary: initialSummary,
    calls: 0,
    completed: 0,
    goals: [] as unknown[],
    unexpectedRequests: [] as string[],
    nextResponseGate: null as Promise<void> | null,
    ...initial,
  };
  await page.addInitScript(() =>
    sessionStorage.setItem("devpilot.access_token", "planning-test-token"),
  );
  // Every API request is intercepted, including unexpected writes.
  await page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (req.method() === "GET" && path.endsWith("/planning/drafts"))
      return route.fulfill({ json: { items: drafts, total: drafts.length, offset: 0, limit: 20 } });
    const draft = drafts.find(item => path.endsWith(`/planning/drafts/${item.id}`));
    if (req.method() === "GET" && draft) return route.fulfill({ json: draft });
    if (req.method() === "GET" && path.endsWith("/conversations"))
      return route.fulfill({ json: [] });
    if (req.method() === "GET" && path.endsWith("/me"))
      return route.fulfill({
        json: { id: randomUUID(), username: "规划测试", role: "member" },
      });
    if (req.method() === "GET" && path === `/api/v1/projects/${id}`)
      return route.fulfill({
        json: {
          id,
          name: "餐厅外卖网站",
          description: "在线点餐与订单管理",
          created_at: "2026-09-14T00:00:00Z",
          updated_at: "2026-09-14T00:00:00Z",
        },
      });
    if (
      req.method() === "GET" &&
      path === `/api/v1/projects/${id}/planning`
    )
      return route.fulfill({
        json: {
          mode: state.mode,
          configured: state.configured,
          ready_documents: state.ready,
          task_count: 3,
        },
      });
    if (
      req.method() === "POST" &&
      path === `/api/v1/projects/${id}/planning/drafts/stream`
    ) {
      state.calls++;
      state.goals.push(req.postDataJSON());
      const fail = state.fail;
      const response = {
        mode: state.mode,
        proposal: {
          summary: state.summary,
          assumptions: [unsafeAssumption],
          risks: ["并发下单可能造成库存超卖，需要原子扣减与回滚。"],
          tasks: [
            {
              draft_id: "T1",
              title: "实现订单收货信息",
              description: unsafeDescription,
              priority: 1,
              acceptance_criteria:
                "缺少收货人、手机号或地址时禁止提交。\n输入合法信息后可以进入订单确认页。",
              dependencies: [],
              source_ids: [1],
            },
            {
              draft_id: "T2",
              title: "校验库存与提交订单",
              description: "复用订单信息，在提交时检查可售库存。",
              priority: 2,
              acceptance_criteria: "库存不足时拒绝下单并显示明确原因。",
              dependencies: ["T1"],
              source_ids: [1],
            },
          ],
        },
        sources: [
          {
            source_id: 1,
            document_id: randomUUID(),
            filename: "订单规则.md",
            chunk_index: 0,
            heading: "订单管理",
            text: sourceText,
          },
        ],
        tool_calls: [
          { name: "search_documents", status: "success", item_count: 1 },
          { name: "read_task_board", status: "success", item_count: 3 },
        ],
        board_task_count: 3,
        persisted: false,
      };
      const gate = state.nextResponseGate;
      state.nextResponseGate = null;
      if (gate) await gate;
      const draft = { ...savedDraft(id, req.postDataJSON().goal, response), id: randomUUID() };
      if (!fail) drafts.unshift(draft);
      try {
        return await route.fulfill(
          fail
            ? {
                status: 502,
                json: {
                  error: {
                    code: "planning_unavailable",
                    message: "模型服务暂时不可用",
                    request_id: "planning-test-request",
                  },
                },
              }
            : finalResponse("draft", draft),
        );
      } finally {
        state.completed++;
      }
    }
    state.unexpectedRequests.push(`${req.method()} ${path}`);
    return route.fulfill({ status: 404, json: {} });
  });
  await page.goto(`/projects/${id}?tab=planning`);
  await expect(page.getByRole("button", { name: "刷新规划状态" })).toBeEnabled();
  return {
    id,
    state,
    holdNextResponse() {
      let release!: () => void;
      state.nextResponseGate = new Promise<void>((resolve) => {
        release = resolve;
      });
      return release;
    },
  };
}

test("长方案在结果区滚动，预览和审批切换保留目标与草案", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  const { state } = await planning(page);
  state.summary = "下单时检查库存并防止重复提交。".repeat(100);
  await page.getByLabel("你想完成什么目标？").fill("完善下单流程");
  await page.getByRole("button", { name: "生成任务草案", exact: true }).click();
  const preview = page.getByRole("region", { name: "任务方案预览" });
  await expect(preview).toBeVisible();
  await preview.getByLabel("已完成只读工具调用", { exact: true }).scrollIntoViewIfNeeded();
  await expect(page.getByRole("navigation", { name: "项目功能" })).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight + 1)).toBe(true);
  await page.getByRole("button", { name: "审批记录", exact: true }).click();
  await expect(preview).toBeHidden();
  await expect(page.getByRole("button", { name: "刷新审批记录", exact: true })).toBeInViewport();
  await expect(page.getByLabel("你想完成什么目标？")).toHaveValue("完善下单流程");
  await page.getByRole("button", { name: "草案预览", exact: true }).click();
  await expect(preview).toContainText(state.summary);
  expect(state.calls).toBe(1);
});

test("任务规划入口展示已保存草案、验收依赖和安全引用，双端布局正常", async ({
  page,
}) => {
  const { id, state } = await planning(page);
  const navigation = page.getByRole("navigation", { name: "项目功能" });
  await expect(
    navigation.getByRole("link", { name: "任务规划", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { name: "任务规划", exact: true })).toBeVisible();
  await navigation.getByRole("link", { name: "项目概览", exact: true }).click();
  await expect(page.getByRole("heading", { name: "需求说明", exact: true })).toBeVisible();
  await navigation.getByRole("link", { name: "任务规划", exact: true }).click();
  await expect(page).toHaveURL(`/projects/${id}?tab=planning`);
  await expect(page.getByRole("status")).toContainText("演示模式");
  const conversation = page.getByRole("region", { name: "规划对话" });
  await expect(conversation).toContainText("规划目标");
  await expect(page.getByLabel("任务草案工作区")).toContainText("任务计划将在这里展开");

  await page.getByLabel("你想完成什么目标？").fill("  完成可靠的下单流程  ");
  await page.getByRole("button", { name: "生成任务草案", exact: true }).click();
  const preview = page.getByRole("region", { name: "任务方案预览" });
  await expect(preview).toBeVisible();
  await expect(page.getByLabel("本次规划目标")).toContainText("完成可靠的下单流程");
  await expect(preview).toContainText("方案摘要");
  await expect(preview).toContainText(initialSummary);
  await expect(preview).toContainText(unsafeAssumption);
  const assumptions = preview.getByLabel("规划假设", { exact: true });
  await assumptions.locator("summary").click();
  await expect(assumptions.getByText(unsafeAssumption, { exact: true })).toBeVisible();
  await expect(preview).toContainText("并发下单可能造成库存超卖，需要原子扣减与回滚。");
  const firstTask = preview.getByRole("article", {
    name: "任务 T1：实现订单收货信息",
    exact: true,
  });
  const secondTask = preview.getByRole("article", {
    name: "任务 T2：校验库存与提交订单",
    exact: true,
  });
  await expect(firstTask).toContainText(unsafeDescription);
  await expect(firstTask).toContainText(/P1|优先级\s*[：:]?\s*1/);
  await expect(firstTask).toContainText("缺少收货人、手机号或地址时禁止提交。");
  await expect(firstTask).toContainText("输入合法信息后可以进入订单确认页。");
  await expect(secondTask).toContainText(/P2|优先级\s*[：:]?\s*2/);
  await expect(secondTask).toContainText("T1");
  await expect(secondTask).toContainText("实现订单收货信息");
  await expect(secondTask).toContainText("库存不足时拒绝下单并显示明确原因。");
  await expect(firstTask).toContainText("[1]");
  await expect(secondTask).toContainText("[1]");
  await expect(preview).toContainText("已完成只读工具调用");
  const toolCalls = preview.getByLabel("已完成只读工具调用", { exact: true });
  await toolCalls.locator("summary").click();
  await expect(toolCalls).toContainText("检索项目文档 · 已完成 · 1 项");
  await expect(toolCalls).toContainText("读取任务看板 · 已完成 · 3 项");
  await expect(
    page.getByText("草案生成后自动保存", { exact: false }),
  ).toBeVisible();
  await expect(
    preview.getByRole("button", { name: "提交这一版", exact: true }),
  ).toBeVisible();
  const source = preview.getByLabel("来源 1", { exact: true });
  await expect(source.locator("summary")).toHaveText("[1] 订单规则.md · 第 1 个片段");
  await source.locator("summary").click();
  await expect(source.locator("blockquote")).toHaveText(sourceText);
  await expect(preview.locator("img, script, iframe")).toHaveCount(0);
  await source.locator("summary").click();
  await toolCalls.locator("summary").click();
  await assumptions.locator("summary").click();
  expect(state.goals).toEqual([{ goal: "完成可靠的下单流程" }]);
  expect(state.unexpectedRequests).toEqual([]);

  const desktopConversation = await conversation.boundingBox();
  const desktopPreview = await preview.boundingBox();
  expect(desktopConversation).not.toBeNull();
  expect(desktopPreview).not.toBeNull();
  expect(desktopConversation!.x + desktopConversation!.width).toBeLessThan(desktopPreview!.x);

  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/screenshots/task-planning-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 375, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBe(true);
  const mobileConversation = await conversation.boundingBox();
  const mobilePreview = await preview.boundingBox();
  expect(mobileConversation!.y + mobileConversation!.height).toBeLessThanOrEqual(mobilePreview!.y);
  await page.getByLabel("你想完成什么目标？").focus();
  await expect(page.getByLabel("你想完成什么目标？")).toBeInViewport();
  await page.getByRole("button", { name: "重新生成草案", exact: true }).scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", { name: "重新生成草案", exact: true })).toBeInViewport();
  await page.screenshot({
    path: "test-results/screenshots/task-planning-mobile.png",
    fullPage: true,
  });
});

test("建议目标只填入并聚焦，任务可用键盘展开且尊重减少动态效果", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  const { state } = await planning(page);
  const input = page.getByLabel("你想完成什么目标？");
  const suggestion = page.getByRole("button", { name: "规划下一阶段开发", exact: true });
  await expect(input).toBeInViewport();
  await expect(page.getByRole("button", { name: "生成任务草案", exact: true })).toBeInViewport();
  expect(await suggestion.evaluate((element) => parseFloat(getComputedStyle(element).transitionDuration))).toBeGreaterThan(0);
  await suggestion.click();
  await expect(input).toHaveValue("根据项目资料，规划下一阶段的开发任务，明确优先级和验收标准。");
  await expect(input).toBeFocused();
  expect(state.calls).toBe(0);
  await page.getByRole("button", { name: "生成任务草案", exact: true }).click();
  const preview = page.getByRole("region", { name: "任务方案预览" });
  await expect(preview).toBeVisible();
  await expect(preview.getByRole("heading", { name: "任务方案预览", exact: true })).toHaveCSS("font-size", "18px");
  expect(await preview.evaluate((element) => parseFloat(getComputedStyle(element).animationDuration))).toBeGreaterThan(0);
  const firstTask = preview.getByRole("article", { name: "任务 T1：实现订单收货信息", exact: true });
  const taskDetails = firstTask.locator("details");
  const taskSummary = taskDetails.locator("summary");
  await expect(taskDetails).toHaveJSProperty("open", false);
  await taskSummary.focus();
  await taskSummary.press("Enter");
  await expect(taskDetails).toHaveJSProperty("open", true);
  await expect(firstTask.locator("dd").first()).toBeVisible();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(preview).toHaveCSS("animation-duration", "0s");
  await expect(taskSummary).toHaveCSS("transition-duration", "0s");
  await taskSummary.press("Enter");
  await expect(taskDetails).toHaveJSProperty("open", false);
  await expect(firstTask.locator("dd").first()).toBeHidden();
  expect(state.calls).toBe(1);
  expect(state.unexpectedRequests).toEqual([]);
});

test("重新生成开始立即移除旧草案，新方案对应新目标", async ({ page }) => {
  const { state, holdNextResponse } = await planning(page);
  const input = page.getByLabel("你想完成什么目标？");
  const preview = page.getByRole("region", { name: "任务方案预览" });
  await input.fill("先完成下单流程");
  await page.getByRole("button", { name: "生成任务草案", exact: true }).click();
  await expect(preview).toContainText(initialSummary);
  await input.fill("优先完成库存一致性校验");
  state.summary = "此次方案聚焦库存一致性与失败回滚。";
  const release = holdNextResponse();
  try {
    await page.getByRole("button", { name: "重新生成草案", exact: true }).click();
    await expect.poll(() => state.calls).toBe(2);
    await expect(page.getByRole("button", { name: "取消生成", exact: true })).toBeVisible();
    await expect(preview).toHaveCount(0);
    await expect(page.getByText(initialSummary, { exact: true })).toHaveCount(0);
  } finally {
    release();
  }
  await expect(preview).toContainText(state.summary);
  await expect(page.getByLabel("本次规划目标")).toContainText("优先完成库存一致性校验");
  await expect(preview).not.toContainText(initialSummary);
  expect(state.goals).toEqual([
    { goal: "先完成下单流程" },
    { goal: "优先完成库存一致性校验" },
  ]);
  expect(state.unexpectedRequests).toEqual([]);
});

test("模型失败保留规划目标，重试成功后展示草案", async ({ page }) => {
  const { state } = await planning(page);
  state.fail = true;
  const input = page.getByLabel("你想完成什么目标？");
  await input.fill("为订单增加库存校验");
  await page.getByRole("button", { name: "生成任务草案", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("模型服务暂时不可用");
  await expect(page.getByRole("alert")).toContainText("请求编号：planning-test-request");
  await expect(input).toHaveValue("为订单增加库存校验");
  await expect(page.getByRole("region", { name: "任务方案预览" })).toHaveCount(0);
  state.fail = false;
  await page.getByRole("button", { name: "生成任务草案", exact: true }).click();
  await expect(page.getByRole("region", { name: "任务方案预览" })).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  expect(state.goals).toEqual([
    { goal: "为订单增加库存校验" },
    { goal: "为订单增加库存校验" },
  ]);
  expect(state.unexpectedRequests).toEqual([]);
});

test("取消生成保留目标，迟到响应不会覆盖重试结果", async ({ page }) => {
  const { state, holdNextResponse } = await planning(page);
  const input = page.getByLabel("你想完成什么目标？");
  const preview = page.getByRole("region", { name: "任务方案预览" });
  const release = holdNextResponse();
  try {
    await input.fill("完成订单校验");
    await page.getByRole("button", { name: "生成任务草案", exact: true }).click();
    await expect.poll(() => state.calls).toBe(1);
    await page.getByRole("button", { name: "取消生成", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText(/已取消|已停止/);
    await expect(input).toHaveValue("完成订单校验");
    await expect(input).toBeEnabled();
    await expect(input).toBeFocused();
    await expect(preview).toHaveCount(0);
    state.summary = "取消后重试得到的最新方案。";
    await page.getByRole("button", { name: "生成任务草案", exact: true }).click();
    await expect(preview).toContainText(state.summary);
  } finally {
    release();
  }
  await expect.poll(() => state.completed).toBe(2);
  await expect(preview).toContainText(state.summary);
  await expect(preview).not.toContainText(initialSummary);
  expect(state.calls).toBe(2);
  expect(state.unexpectedRequests).toEqual([]);
});

test("无文档和模型未配置时禁止生成，刷新后恢复真实模型模式", async ({ page }) => {
  const { id, state } = await planning(page, { ready: 0 });
  const input = page.getByLabel("你想完成什么目标？");
  const generate = page.getByRole("button", { name: "生成任务草案", exact: true });
  await expect(input).toBeDisabled();
  await expect(generate).toBeDisabled();
  await expect(page.getByRole("link", { name: "知识库上传资料" })).toHaveAttribute(
    "href",
    `/projects/${id}?tab=documents`,
  );
  state.ready = 1;
  state.mode = "live";
  state.configured = false;
  await page.getByRole("button", { name: "刷新规划状态" }).click();
  await expect(page.getByRole("alert")).toContainText("MODEL_NAME");
  await expect(input).toBeDisabled();
  await expect(generate).toBeDisabled();
  await expect(page.getByRole("status")).toContainText("真实模型模式");
  expect(state.calls).toBe(0);
  state.configured = true;
  await page.getByRole("button", { name: "刷新规划状态" }).click();
  await expect(input).toBeEnabled();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await input.fill("按现有资料规划订单流程");
  await generate.click();
  await expect(page.getByRole("region", { name: "任务方案预览" })).toBeVisible();
  expect(state.calls).toBe(1);
  expect(state.unexpectedRequests).toEqual([]);
});

test("关闭预览或刷新后可以打开已保存草案，不再次生成", async ({ page }) => {
  const { state } = await planning(page);
  const preview = page.getByRole("region", { name: "任务方案预览" });
  await page.getByLabel("你想完成什么目标？").fill("完成点餐网站第一版");
  await page.getByRole("button", { name: "生成任务草案", exact: true }).click();
  await expect(preview).toBeVisible();
  await page.getByRole("button", { name: "关闭预览", exact: true }).click();
  await expect(preview).toHaveCount(0);
  const open = page.getByRole("button", { name: "打开草案：完成点餐网站第一版", exact: true });
  await open.click();
  await expect(preview).toContainText(initialSummary);
  await page.reload();
  await expect(preview).toHaveCount(0);
  await open.click();
  await expect(preview).toContainText(initialSummary);
  await expect(preview).toContainText("已保存 · 第 1 版");
  expect(state.calls).toBe(1);
  expect(state.unexpectedRequests).toEqual([]);
});
