import { test, expect } from "@playwright/test";
import { setupUnified, sendQuestion } from "./unified_fixture";

test("旧检查链接展示三类发现、对应任务和真实范围，内容安全且双端可读", async ({ page }) => {
  const { state } = await setupUnified(page, "assistant", { mode: "live" });
  await expect(page.getByRole("button", { name: "检查需求缺口", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByRole("link", { name: "需求检查", exact: true })).toHaveCount(0);
  await sendQuestion(page, "对照需求文档，看看现有任务还漏了什么，有哪些需求需要确认？");
  const detail = page.getByLabel("结果详情", { exact: true });
  await expect(detail.getByRole("region", { name: "已有对应任务", exact: true })).toContainText("实现文档上传 · 进行中");
  await expect(detail.getByRole("region", { name: "可能遗漏", exact: true })).toContainText("删除文档");
  await expect(detail.getByRole("region", { name: "需要确认", exact: true })).toContainText("删除时是否清理索引");
  const scope = detail.getByRole("region", { name: "依据与检查范围", exact: true });
  await expect(scope).toContainText("未逐份检查全文");
  await expect(scope).toContainText("1 个片段");
  await expect(scope).toContainText("<script>window.injected=true</script>");
  const citation = detail.getByRole("region", { name: "可能遗漏", exact: true }).getByRole("link", { name: "依据 [1]", exact: true });
  const href = await citation.getAttribute("href");
  expect(href).toMatch(/^#check-source-chat-artifact-/);
  await citation.click();
  await expect(detail.locator('[id="' + href!.slice(1) + '"]')).toBeInViewport();
  await detail.getByText("本次读取的看板任务（1 项）", { exact: true }).click();
  await expect(scope).toContainText("上传成功后可查询状态");
  await expect(detail.locator("img, script, iframe")).toHaveCount(0);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: "test-results/screenshots/requirement-check-desktop.png", fullPage: true, animations: "disabled" });
  for (const width of [390, 360, 768]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(page.getByRole("button", { name: "关闭结果详情", exact: true })).toBeVisible();
  }
  await page.screenshot({ path: "test-results/screenshots/requirement-check-mobile.png", fullPage: true, animations: "disabled" });
  expect(state.calls[0]!.payload).toMatchObject({ question: "对照需求文档，看看现有任务还漏了什么，有哪些需求需要确认？", intent: "requirement_check" });
  expect(state.unexpected).toEqual([]);
});

test("没有遗漏允许空建议，资料不足和演示工件不能冒充检查完成", async ({ page }) => {
  const { state } = await setupUnified(page, "assistant", { mode: "live" });
  state.workflow.report!.missing = [];
  await sendQuestion(page, "检查上传与删除需求");
  const detail = page.getByLabel("结果详情", { exact: true });
  await expect(detail.getByRole("region", { name: "可能遗漏", exact: true })).toContainText("在本次已读片段中未发现明显遗漏");
  state.workflow.status = "insufficient_evidence"; state.workflow.report = null;
  state.workflow.answer = "没有检索到可用于对照的需求片段，无法判断是否遗漏。";
  await sendQuestion(page, "只检查索引清理规则");
  await expect(detail.getByText("资料不足不等于没有遗漏。", { exact: true })).toBeVisible();
  await expect(detail.getByRole("region", { name: "可能遗漏", exact: true })).toHaveCount(0);
  state.workflow.status = "demo"; state.workflow.mode = "mock"; state.mode = "mock";
  state.workflow.answer = "演示模式未调用聊天模型，不判断需求覆盖或遗漏。";
  await page.getByRole("button", { name: "刷新问答状态", exact: true }).click();
  await sendQuestion(page, "演示检查文档管理需求");
  await expect(detail.getByText(state.workflow.answer, { exact: true })).toBeVisible();
  await expect(detail.getByRole("region", { name: "可能遗漏", exact: true })).toHaveCount(0);
  expect(state.calls).toHaveLength(3); expect(state.unexpected).toEqual([]);
});

test("取消等待忽略迟到结果，重新提交并离开返回仍能恢复已保存报告", async ({ page }) => {
  const { state, hold } = await setupUnified(page, "assistant", { mode: "live" });
  const release = hold();
  try {
    await sendQuestion(page, "检查文档管理需求");
    await expect.poll(() => state.calls.length).toBe(1);
    await page.getByRole("button", { name: "停止等待", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText(/已取消|已停止/);
    state.workflow.answer = "第二次检查结果";
    await page.getByRole("button", { name: "重试此问题", exact: true }).click();
    await expect(page.getByLabel("结果详情", { exact: true })).toContainText("第二次检查结果");
  } finally { release(); }
  await expect.poll(() => state.completed).toBe(2);
  await expect(page.getByLabel("结果详情", { exact: true })).toContainText("第二次检查结果");
  await page.getByRole("link", { name: "项目概览", exact: true }).click();
  await page.getByRole("link", { name: "项目助手", exact: true }).click();
  await page.getByRole("button", { name: "打开需求检查报告", exact: true }).click();
  await expect(page.getByLabel("结果详情", { exact: true })).toContainText("第二次检查结果");
  expect(state.calls).toHaveLength(2); expect(state.unexpected).toEqual([]);
});

test("变更冲突保留问题和用途可重试，新对话不展示旧报告", async ({ page }) => {
  const { state } = await setupUnified(page, "assistant", { mode: "live" });
  state.failure = 409;
  state.error = { code: "workflow_context_changed", message: "检查期间任务发生变化，请重新检查", request_id: "workflow-test-id" };
  await sendQuestion(page, "只检查文档删除需求");
  await expect(page.getByRole("alert")).toContainText("workflow-test-id");
  await expect(page.getByRole("log")).toContainText("只检查文档删除需求");
  state.failure = 0;
  await page.getByRole("button", { name: "重试此问题", exact: true }).click();
  await expect(page.getByLabel("结果详情", { exact: true }).getByRole("region", { name: "可能遗漏", exact: true })).toBeVisible();
  expect(state.calls[1]!.payload).toEqual(state.calls[0]!.payload);
  await page.getByRole("button", { name: "新对话", exact: true }).click();
  await expect(page.getByLabel("结果详情", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "打开需求检查报告", exact: true })).toHaveCount(0);
  expect(state.unexpected).toEqual([]);
});

test("无文档也能自动查询任务，显式用途可切换到需求检查", async ({ page }) => {
  const { state } = await setupUnified(page, "assistant", { mode: "live", ready: 0 });
  const task = state.workflow.scope.tasks[0]!;
  state.answer = { mode: "live", basis: "project", status: "answered", answer: "找到一项进行中任务", tasks: [task], sources: [],
    tool_calls: [{ name: "read_task_board", status: "success", item_count: 1 }], artifacts: [] };
  await page.getByRole("button", { name: "自动处理", exact: true }).click();
  await sendQuestion(page, "看板中有哪些进行中的任务？");
  const tasks = page.getByLabel("查询到的任务", { exact: true });
  await tasks.locator("summary").click();
  await expect(tasks).toContainText("实现文档上传");
  expect(state.calls[0]!.payload.intent).toBe("auto");
  state.answer = null;
  state.workflow.status = "insufficient_evidence"; state.workflow.report = null; state.workflow.sources = [];
  state.workflow.answer = "没有需求依据，无法检查遗漏。";
  await page.getByRole("button", { name: "检查需求缺口", exact: true }).click();
  await sendQuestion(page, "对照文档检查遗漏");
  await expect(page.getByLabel("结果详情", { exact: true })).toContainText("资料不足不等于没有遗漏。");
  expect(state.calls[1]!.payload.intent).toBe("requirement_check");
  expect(state.unexpected).toEqual([]);
});

test("空输入禁用发送，未配置模型时提示且禁用请求", async ({ page }) => {
  const { state } = await setupUnified(page, "assistant", { mode: "live" });
  await page.getByLabel("你想了解什么？").fill("   ");
  await expect(page.getByRole("button", { name: "发送问题", exact: true })).toBeDisabled();
  expect(state.calls).toHaveLength(0);
  state.configured = false;
  await page.getByRole("button", { name: "刷新问答状态", exact: true }).click();
  await expect(page.getByRole("button", { name: "发送问题", exact: true })).toBeDisabled();
  await expect(page.getByRole("alert")).toContainText("聊天模型尚未配置，请联系管理员完成配置后刷新。");
  expect(state.calls).toHaveLength(0); expect(state.unexpected).toEqual([]);
});
