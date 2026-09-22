import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const contract = JSON.parse(readFileSync(new URL("../../src/types/stream.contract.json", import.meta.url), "utf8"));
import type { ApprovalVO } from "../../src/types/api";

test("多方案、多任务时列表和详情独立滚动，审批操作始终可达", async ({ page }) => {
  const sample = contract.events.find((e: { type: string; kind?: string; result?: unknown }) => e.type === "final" && e.kind === "approval");
  const approval = structuredClone(sample!.result) as ApprovalVO;
  approval.plan.proposal.tasks = Array.from({ length: 10 }, (_, i) => ({
    ...approval.plan.proposal.tasks[0]!, draft_id: `T${i + 1}`,
    title: `任务 ${i + 1}：校验订单与库存状态`,
    description: "校验库存和地址，发生异常时保留输入并允许重试。".repeat(40),
  }));
  const items = Array.from({ length: 20 }, (_, i) => ({ ...approval, id: `${i}`, goal: `第 ${i + 1} 份计划：完善订单校验和库存管理，补充异常测试。` }));
  await page.addInitScript(() => sessionStorage.setItem("devpilot.access_token", "layout-test-token"));
  await page.route("**/api/v1/**", route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/me")) return route.fulfill({ json: { id: "reviewer", username: "审核", role: "reviewer" } });
    if (path.endsWith("/approvals")) return route.fulfill({ json: { items, total: 20, offset: 0, limit: 20 } });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/reviewer");
  const list = page.getByRole("region", { name: "审批列表", exact: true });
  await list.getByRole("button").first().click();
  const detail = page.getByRole("region", { name: "审阅方案", exact: true });
  const approve = page.getByRole("button", { name: "批准并加入看板", exact: true });
  await expect(approve).toBeInViewport();
  await detail.locator("article summary").first().click();
  await detail.locator("article").last().scrollIntoViewIfNeeded();
  await list.getByRole("button").last().scrollIntoViewIfNeeded();
  await expect(approve).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight + 1)).toBe(true);
  await page.getByRole("button", { name: "修改任务方案", exact: true }).click();
  await page.getByLabel("任务标题", { exact: true }).last().fill("最后一项已修改");
  await expect(page.getByRole("button", { name: "修改后批准并加入看板", exact: true })).toBeInViewport();
  await page.getByRole("button", { name: "收起修改", exact: true }).click();
  await detail.locator("article summary").first().click();
  await list.evaluate(el => el.scrollTop = 0);
  await detail.locator(".work-scroll").evaluate(el => el.scrollTop = 0);
  await page.screenshot({ path: "test-results/screenshots/reviewer-many-desktop.png", fullPage: true, animations: "disabled" });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await approve.scrollIntoViewIfNeeded();
  await expect(approve).toBeInViewport();
});
