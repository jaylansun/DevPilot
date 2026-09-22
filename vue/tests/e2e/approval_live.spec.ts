import { test, expect, type Page } from "@playwright/test";

const api = process.env.DEVPILOT_APPROVAL_API;
const project = "22222222-2222-4222-8222-222222222222";
test.skip(!api, "需要启动独立的审批集成验收服务");

async function login(page: Page, username: string) {
  await page.route("**/api/v1/**", async route => {
    const url = new URL(route.request().url());
    const response = await route.fetch({ url: api + url.pathname + url.search });
    await route.fulfill({ response });
  });
  await page.goto("/login");
  await page.getByLabel("用户名", { exact: true }).fill(username);
  await page.getByLabel("密码", { exact: true }).fill("day12-test-password");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

test("真实 API：成员提交、刷新保留、审批人修改批准、任务进入看板", async ({ page, browser }) => {
  await login(page, "day12_member");
  await page.goto(`/projects/${project}?tab=planning`);
  await page.getByRole("button", { name: "提交与审批", exact: true }).click();
  await page.getByLabel("你想完成什么目标？").fill("完善订单流程并核对重复提交规则");
  await page.getByRole("button", { name: "生成并提交审批", exact: true }).click();
  const records = page.getByRole("region", { name: "持久规划与审批" });
  await expect(records.getByRole("status")).toHaveText("等待审批");
  await page.reload();
  await page.getByRole("button", { name: "提交与审批", exact: true }).click();
  await expect(records.getByText("等待审批", { exact: true })).toBeVisible();
  await records.getByRole("button", { name: "查看方案" }).click();
  await expect(records.getByRole("region", { name: "审批方案详情" })).toBeVisible();

  const reviewer = await browser.newPage();
  try {
    await login(reviewer, "day12_reviewer");
    await reviewer.getByRole("button", { name: /第十二天审批验收/ }).click();
    await reviewer.getByRole("button", { name: "修改任务方案", exact: true }).click();
    await reviewer.getByLabel("任务标题", { exact: true }).first().fill("审批确认的订单校验任务");
    await reviewer.screenshot({ path: "test-results/screenshots/day12-reviewer-desktop.png", fullPage: true });
    await reviewer.setViewportSize({ width: 390, height: 844 });
    await expect(reviewer.getByLabel("任务标题", { exact: true }).first()).toBeVisible();
    expect(await reviewer.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBeTruthy();
    await reviewer.screenshot({ path: "test-results/screenshots/day12-reviewer-mobile.png", fullPage: true });
    await reviewer.getByRole("button", { name: "修改后批准并加入看板", exact: true }).click();
    await expect(reviewer.getByText(/已创建 \d+ 项任务/)).toBeVisible();
  } finally { await reviewer.close(); }
  await page.reload();
  await page.getByRole("button", { name: "提交与审批", exact: true }).click();
  await expect(records.getByText("已加入看板", { exact: true })).toBeVisible();
  await page.getByRole("navigation", { name: "项目功能" }).getByRole("link", { name: "任务看板", exact: true }).click();
  await expect(page.getByText("审批确认的订单校验任务", { exact: true })).toBeVisible();
});
