import { readFileSync, writeFileSync } from "node:fs";
import { test, expect, type Page } from "@playwright/test";

// 由 scripts/test_day13.py 启动隔离环境；浏览器不拦截或伪造 API 响应。
const phase = process.env.DEVPILOT_JOURNEY_PHASE;
const stateFile = process.env.DEVPILOT_JOURNEY_STATE;
test.skip(!phase || !stateFile, "使用第十三天隔离验收脚本运行，禁止连接日常业务环境");
test.setTimeout(60_000);
const projectName = "第十三天全流程验收";
const filename = "订单验收规则.md";
type Saved = { project: string; approval: string; taskIds?: string[] };

async function login(page: Page, role: "member" | "reviewer") {
  await page.goto("/login");
  await page.getByLabel("用户名", { exact: true }).fill(`day13_${role}`);
  await page.getByLabel("密码", { exact: true }).fill("day13-test-password");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(role === "member" ? /\/projects$/ : /\/reviewer$/);
}
async function headers(page: Page) {
  return { Authorization: `Bearer ${await page.evaluate(() => sessionStorage.getItem("devpilot.access_token"))}` };
}
async function tab(page: Page, name: string) {
  await page.getByRole("navigation", { name: "项目功能" }).getByRole("link", { name, exact: true }).click();
}
async function ask(page: Page) {
  await tab(page, "AI 问答");
  await page.getByLabel("你想了解什么？").fill("订单重复提交如何处理？");
  await page.getByRole("button", { name: "发送问题", exact: true }).click();
  const citation = page.locator("summary").filter({ hasText: filename });
  await expect(citation).toBeVisible();
  await citation.click();
  await expect(page.locator("blockquote")).toContainText("同一个订单不得重复提交");
}

test("重启前：真实登录、建项目、上传索引、提问、需求检查、提交审批", async ({ page }) => {
  test.skip(phase !== "prepare");
  await login(page, "member");
  await page.getByRole("button", { name: "新建项目", exact: true }).click();
  await page.getByLabel("项目名称").fill(projectName);
  await page.getByLabel("需求说明").fill("订单提交与重复校验");
  await page.getByRole("button", { name: "创建项目", exact: true }).click();
  await page.getByRole("link", { name: "打开项目", exact: true }).click();
  const project = new URL(page.url()).pathname.split("/").at(-1)!;
  await tab(page, "知识库");
  await page.getByLabel("选择知识库文档").setInputFiles({
    name: filename, mimeType: "text/markdown",
    buffer: Buffer.from("# 订单规则\n同一个订单不得重复提交。创建订单必须填写配送地址。库存不足时拒绝下单。"),
  });
  await page.getByRole("button", { name: "上传文档", exact: true }).click();
  await expect(page.getByRole("article", { name: filename, exact: true })).toContainText("已就绪", { timeout: 30_000 });
  await ask(page);
  await tab(page, "需求检查");
  await page.getByRole("button", { name: "开始检查", exact: true }).click();
  await expect(page.getByRole("region", { name: "依据与检查范围" })).toContainText(filename);
  await tab(page, "任务规划");
  await page.getByLabel("你想完成什么目标？").fill("实现订单校验并补充验收测试");
  let generations = 0;
  page.on("request", request => { if (request.url().endsWith("/planning/drafts/stream")) generations++; });
  await page.getByRole("button", { name: "生成任务草案", exact: true }).click();
  await page.getByRole("button", { name: "编辑草案", exact: true }).click();
  await page.getByLabel("任务标题", { exact: true }).first().fill("成员确认的订单校验");
  await page.getByRole("button", { name: "保存修改", exact: true }).click();
  await expect(page.getByRole("region", { name: "草案编辑与送审" })).toContainText("第 2 版");
  await page.reload();
  await page.getByRole("button", { name: "打开草案：实现订单校验并补充验收测试", exact: true }).click();
  await expect(page.getByRole("region", { name: "任务方案预览" })).toContainText("成员确认的订单校验");
  await page.getByRole("button", { name: "提交这一版", exact: true }).click();
  const records = page.getByRole("region", { name: "持久规划与审批" });
  await expect(records.getByRole("status")).toHaveText("等待审批");
  const response = await page.request.get(`/api/v1/projects/${project}/conversations`, { headers: await headers(page) });
  expect(response.ok()).toBe(true);
  const conversations = await response.json();
  expect(conversations).toHaveLength(1);
  expect(conversations[0].approval.plan.proposal.tasks[0].title).toBe("成员确认的订单校验");
  expect(generations).toBe(1);
  writeFileSync(stateFile!, JSON.stringify({ project, approval: conversations[0].approval.id } satisfies Saved));
});

test("重启后：索引和待审批保留、修改批准、幂等重试、看板更新", async ({ page, browser }) => {
  test.skip(phase !== "approve");
  const saved: Saved = JSON.parse(readFileSync(stateFile!, "utf8"));
  await login(page, "member");
  await page.goto(`/projects/${saved.project}?tab=documents`);
  await tab(page, "知识库");
  await expect(page.getByRole("article", { name: filename, exact: true })).toContainText("已就绪");
  await ask(page); // 必须读到上一进程写入的真实 Chroma 数据。
  await tab(page, "任务规划");
  await page.getByRole("button", { name: "审批记录", exact: true }).click();
  const records = page.getByRole("region", { name: "持久规划与审批" });
  await expect(records.getByText("等待审批", { exact: true })).toBeVisible();
  const reviewerContext = await browser.newContext({ baseURL: new URL(page.url()).origin });
  const reviewer = await reviewerContext.newPage();
  try {
    await login(reviewer, "reviewer");
    await reviewer.getByRole("button", { name: new RegExp(projectName) }).click();
    await expect(reviewer.getByRole("region", { name: "审批方案详情" })).toContainText("成员确认的订单校验");
    await reviewer.getByRole("button", { name: "修改任务方案", exact: true }).click();
    await reviewer.getByLabel("任务标题", { exact: true }).first().fill("审核后的订单校验");
    await reviewer.getByRole("button", { name: "修改后批准并加入看板", exact: true }).click();
    await expect(reviewer.getByText(/已创建 \d+ 项任务/)).toBeVisible();
    const response = await reviewer.request.get(`/api/v1/approvals/${saved.approval}`, { headers: await headers(reviewer) });
    expect(response.ok()).toBe(true);
    const result = await response.json();
    expect(result.status).toBe("approved");
    const retry = await reviewer.request.post(`/api/v1/approvals/${saved.approval}/decide/stream`, {
      headers: await headers(reviewer), data: result.decision,
    });
    expect(retry.ok()).toBe(true);
    const repeated = (await retry.text()).trim().split("\n").map(line => JSON.parse(line)).at(-1);
    expect(repeated.result.created_tasks).toEqual(result.created_tasks);
    saved.taskIds = result.created_tasks.map((task: { task_id: string }) => task.task_id);
    writeFileSync(stateFile!, JSON.stringify(saved));
    await expect(reviewer.getByText(/已创建 \d+ 项任务/)).toBeVisible();
  } finally { await reviewerContext.close(); }
  await page.reload();
  await page.getByRole("button", { name: "审批记录", exact: true }).click();
  await expect(records.getByText("已加入看板", { exact: true })).toBeVisible();
  await tab(page, "任务看板");
  await expect(page.getByText("审核后的订单校验", { exact: true })).toBeVisible();
});

test("再次重启：任务和执行结果持久化，删除文档后不再检索旧索引", async ({ page }) => {
  test.skip(phase !== "verify");
  const saved: Saved = JSON.parse(readFileSync(stateFile!, "utf8"));
  await login(page, "member");
  await page.goto(`/projects/${saved.project}?tab=tasks`);
  await tab(page, "任务看板");
  await expect(page.getByText("审核后的订单校验", { exact: true })).toBeVisible();
  const response = await page.request.get(`/api/v1/projects/${saved.project}/tasks?limit=100`, { headers: await headers(page) });
  expect(response.ok()).toBe(true);
  const tasks = await response.json();
  expect(tasks.total).toBe(saved.taskIds!.length);
  expect(tasks.items.map((task: { id: string }) => task.id).sort()).toEqual(saved.taskIds!.sort());
  await tab(page, "任务规划");
  await page.getByRole("button", { name: "审批记录", exact: true }).click();
  await expect(page.getByText("已加入看板", { exact: true })).toBeVisible();
  await tab(page, "知识库");
  await page.getByRole("button", { name: `删除文档 ${filename}`, exact: true }).click();
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.getByRole("article", { name: filename, exact: true })).toHaveCount(0, { timeout: 15_000 });
  await tab(page, "AI 问答");
  await expect(page.getByLabel("你想了解什么？")).toBeDisabled();
});
