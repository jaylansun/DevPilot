import { test, expect } from "@playwright/test";
import { setupUnified, sendQuestion, initialSummary, unsafeDescription, unsafeAssumption, sourceText } from "./unified_fixture";

test("长方案在详情区滚动，草案与审批切换保留目标和消息", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  const { state } = await setupUnified(page, "planning");
  state.plan.proposal.summary = "下单时检查库存并防止重复提交。".repeat(100);
  await sendQuestion(page, "完善下单流程");
  const detail = page.getByLabel("结果详情", { exact: true });
  await expect(detail).toContainText(state.plan.proposal.summary);
  await detail.getByLabel("草案读取范围", { exact: true }).scrollIntoViewIfNeeded();
  await expect(page.getByRole("button", { name: "发送问题", exact: true })).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight + 1)).toBe(true);
  await page.getByRole("button", { name: "草案与审批", exact: true }).click();
  await page.getByRole("button", { name: "审批记录", exact: true }).click();
  await expect(page.getByRole("button", { name: "刷新审批记录", exact: true })).toBeVisible();
  await page.getByRole("dialog", { name: "草案与审批记录", exact: true }).getByRole("button", { name: "关闭此对话框", exact: true }).click();
  await page.getByRole("button", { name: "草案与审批", exact: true }).click();
  await page.getByRole("button", { name: "已保存草案", exact: true }).click();
  await page.getByRole("button", { name: "打开草案：完善下单流程", exact: true }).click();
  await expect(detail).toContainText(state.plan.proposal.summary);
  await expect(page.getByRole("log")).toContainText("完善下单流程");
  expect(state.calls).toHaveLength(1);
  expect(state.calls[0]!.payload.intent).toBe("task_planning");
  expect(state.unexpected).toEqual([]);
});

test("旧规划链接进入统一助手，保存草案包含验收依赖与安全引用且双端正常", async ({ page }) => {
  const { state } = await setupUnified(page, "planning");
  await expect(page.getByRole("button", { name: "生成任务草案", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("link", { name: "任务规划", exact: true })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "项目助手", exact: true })).toHaveAttribute("aria-current", "page");
  await sendQuestion(page, "  完成可靠的下单流程  ");
  const detail = page.getByLabel("结果详情", { exact: true });
  const preview = detail.getByLabel("任务草案内容", { exact: true });
  await expect(detail).toContainText("目标：完成可靠的下单流程");
  await expect(preview).toContainText(initialSummary);
  await preview.getByLabel("规划假设", { exact: true }).locator("summary").click();
  await expect(preview).toContainText(unsafeAssumption);
  await expect(preview).toContainText("并发下单可能造成库存超卖，需要原子扣减与回滚。");
  const first = preview.getByRole("article", { name: "任务 T1：实现订单收货信息", exact: true });
  const second = preview.getByRole("article", { name: "任务 T2：校验库存与提交订单", exact: true });
  await first.locator("summary").click(); await second.locator("summary").click();
  await expect(first).toContainText(unsafeDescription);
  await expect(first).toContainText("P1");
  await expect(first).toContainText("缺少收货人、手机号或地址时禁止提交。");
  await expect(first).toContainText("输入合法信息后可以进入订单确认页。");
  await expect(second).toContainText("P2");
  await expect(second).toContainText("T1 · 实现订单收货信息");
  await expect(second).toContainText("库存不足时拒绝下单并显示明确原因。");
  const reads = preview.getByLabel("草案读取范围", { exact: true });
  await reads.locator("summary").click();
  await expect(reads).toContainText("检索项目文档 · 已完成 · 1 项");
  await expect(reads).toContainText("读取任务看板 · 已完成 · 3 项");
  await expect(detail.getByRole("button", { name: "提交这一版", exact: true })).toBeVisible();
  const source = preview.getByLabel("来源 1", { exact: true });
  await source.locator("summary").click();
  await expect(source.locator("blockquote")).toHaveText(sourceText);
  await expect(preview.locator("img, script, iframe")).toHaveCount(0);
  expect(state.calls[0]!.payload).toMatchObject({ question: "完成可靠的下单流程", intent: "task_planning" });
  const panel = page.getByRole("region", { name: "项目聊天助手", exact: true });
  const conversation = await panel.locator(":scope > div").first().boundingBox();
  const result = await detail.boundingBox();
  expect(conversation!.x + conversation!.width).toBeLessThanOrEqual(result!.x);
  await page.screenshot({ path: "test-results/screenshots/task-planning-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 375, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  const mobileConversation = await panel.locator(":scope > div").first().boundingBox();
  const mobileResult = await detail.boundingBox();
  expect(mobileConversation!.y + mobileConversation!.height).toBeLessThanOrEqual(mobileResult!.y + 1);
  await page.getByLabel("你想了解什么？").focus();
  await expect(page.getByLabel("你想了解什么？")).toBeInViewport();
  await page.screenshot({ path: "test-results/screenshots/task-planning-mobile.png", fullPage: true });
  expect(state.unexpected).toEqual([]);
});

test("推荐问题只填入并聚焦，任务键盘展开尊重减少动态偏好", async ({ page }) => {
  const { state } = await setupUnified(page, "planning");
  const input = page.getByLabel("你想了解什么？");
  await page.getByRole("button", { name: /^梳理项目：/ }).click();
  await expect(input).toHaveValue("项目资料中描述了哪些核心功能？");
  await expect(input).toBeFocused();
  expect(state.calls).toHaveLength(0);
  await sendQuestion(page, "规划下一阶段的开发任务，明确优先级和验收标准。");
  const first = page.getByLabel("结果详情", { exact: true }).getByRole("article", { name: "任务 T1：实现订单收货信息", exact: true });
  const details = first.locator("details"), summary = details.locator("summary");
  await expect(details).toHaveJSProperty("open", false);
  await summary.focus(); await summary.press("Enter");
  await expect(details).toHaveJSProperty("open", true);
  await expect(first.locator("dd").first()).toBeVisible();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(summary).toHaveCSS("transition-duration", "0s");
  await summary.press("Enter");
  await expect(first.locator("dd").first()).toBeHidden();
  expect(state.calls).toHaveLength(1);
  expect(state.unexpected).toEqual([]);
});

test("重新规划保留历史草案，新结果对应新目标", async ({ page }) => {
  const { state, hold } = await setupUnified(page, "planning");
  await sendQuestion(page, "先完成下单流程");
  const detail = page.getByLabel("结果详情", { exact: true });
  await expect(detail).toContainText(initialSummary);
  state.plan.proposal.summary = "此次方案聚焦库存一致性与失败回滚。";
  const release = hold();
  try {
    await sendQuestion(page, "优先完成库存一致性校验");
    await expect.poll(() => state.calls.length).toBe(2);
    await expect(page.getByRole("button", { name: "停止等待", exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "打开任务草案", exact: true })).toHaveCount(1);
  } finally { release(); }
  await expect(detail).toContainText(state.plan.proposal.summary);
  await expect(detail).toContainText("目标：优先完成库存一致性校验");
  await expect(detail).not.toContainText(initialSummary);
  await expect(page.getByRole("button", { name: "打开任务草案", exact: true })).toHaveCount(2);
  expect(state.calls.map(call => call.payload.question)).toEqual(["先完成下单流程", "优先完成库存一致性校验"]);
  expect(state.unexpected).toEqual([]);
});

test("模型失败保留问题与用途，重试成功交付已保存草案", async ({ page }) => {
  const { state } = await setupUnified(page, "planning"); state.failure = 502;
  await sendQuestion(page, "为订单增加库存校验");
  await expect(page.getByRole("alert")).toContainText("模型服务暂时不可用");
  await expect(page.getByRole("alert")).toContainText("unified-test-request");
  await expect(page.getByRole("log")).toContainText("为订单增加库存校验");
  await expect(page.getByLabel("结果详情", { exact: true })).toHaveCount(0);
  state.failure = 0;
  await page.getByRole("button", { name: "重试此问题", exact: true }).click();
  await expect(page.getByLabel("结果详情", { exact: true })).toContainText("已保存 · 第 1 版");
  expect(state.calls[1]!.payload).toEqual(state.calls[0]!.payload);
  expect(state.calls[0]!.payload.intent).toBe("task_planning");
  expect(state.unexpected).toEqual([]);
});

test("取消生成保留问题，迟到响应不覆盖重试的新方案", async ({ page }) => {
  const { state, hold } = await setupUnified(page, "planning"); const release = hold();
  try {
    await sendQuestion(page, "完成订单校验");
    await expect.poll(() => state.calls.length).toBe(1);
    await page.getByRole("button", { name: "停止等待", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText(/已取消|已停止/);
    await expect(page.getByRole("log")).toContainText("完成订单校验");
    await expect(page.getByLabel("你想了解什么？")).toBeEnabled();
    state.plan.proposal.summary = "取消后重试得到的最新方案。";
    await page.getByRole("button", { name: "重试此问题", exact: true }).click();
    await expect(page.getByLabel("结果详情", { exact: true })).toContainText(state.plan.proposal.summary);
  } finally { release(); }
  await expect.poll(() => state.completed).toBe(2);
  await expect(page.getByLabel("结果详情", { exact: true })).not.toContainText(initialSummary);
  expect(state.calls).toHaveLength(2);
  expect(state.calls[1]!.payload).toEqual(state.calls[0]!.payload);
  expect(state.unexpected).toEqual([]);
});

test("无文档可继续聊天，规划证据错误可重试，模型未配置禁用发送", async ({ page }) => {
  const { state } = await setupUnified(page, "planning", { ready: 0 });
  const input = page.getByLabel("你想了解什么？");
  await expect(input).toBeEnabled();
  await expect(page.getByRole("link", { name: "知识库上传资料", exact: true })).toHaveAttribute("href", "/projects/" + state.projectId + "?tab=documents");
  state.failure = 409; state.error = { code: "planning_no_documents", message: "请先上传项目文档并等待索引完成", request_id: "planning-no-documents" };
  await sendQuestion(page, "按资料规划订单流程");
  await expect(page.getByRole("alert")).toContainText("请先上传项目文档");
  state.ready = 1; state.mode = "live"; state.configured = false;
  await page.getByRole("button", { name: "刷新问答状态", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "聊天模型尚未配置" })).toBeVisible();
  await expect(input).toBeDisabled();
  state.configured = true; state.failure = 0;
  await page.getByRole("button", { name: "刷新问答状态", exact: true }).click();
  await expect(input).toBeEnabled();
  await page.getByRole("button", { name: "重试此问题", exact: true }).click();
  await expect(page.getByLabel("结果详情", { exact: true })).toContainText(initialSummary);
  expect(state.calls).toHaveLength(2); expect(state.unexpected).toEqual([]);
});

test("关闭详情和刷新后能打开消息工件或已保存草案，不再次生成", async ({ page }) => {
  const { state } = await setupUnified(page, "planning");
  await sendQuestion(page, "完成点餐网站第一版");
  const detail = page.getByLabel("结果详情", { exact: true });
  await expect(detail).toContainText(initialSummary);
  await page.getByRole("button", { name: "关闭结果详情", exact: true }).click();
  await expect(detail).toHaveCount(0);
  await page.getByRole("button", { name: "打开任务草案", exact: true }).click();
  await expect(detail).toContainText(initialSummary);
  await page.reload();
  await expect(page.getByRole("button", { name: "打开任务草案", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "草案与审批", exact: true }).click();
  await page.getByRole("button", { name: "打开草案：完成点餐网站第一版", exact: true }).click();
  await expect(detail).toContainText("已保存 · 第 1 版");
  expect(state.calls).toHaveLength(1); expect(state.unexpected).toEqual([]);
});
