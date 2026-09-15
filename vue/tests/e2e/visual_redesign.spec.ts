import { expect, test, type Page } from "@playwright/test";

const projectId = "11111111-1111-4111-8111-111111111111";
const documentId = "22222222-2222-4222-8222-222222222222";
const project = {
  id: projectId, name: "餐厅外卖网站", description: "让顾客在线点餐，让餐厅轻松接单。围绕菜单、下单和订单管理，构建清晰可靠的用户体验。",
  created_at: "2026-09-14T00:00:00Z", updated_at: "2026-09-15T00:00:00Z",
};
const source = {
  source_id: 1, document_id: documentId, filename: "产品需求.md", chunk_index: 0,
  heading: "订单流程", text: "顾客确认商品后填写收货人、手机号和配送地址。系统核对库存，再创建订单。库存不足时保留购物车，并提示顾客调整数量。",
};

// 视觉验收只使用本地拦截数据，不访问业务数据库或真实模型服务。
async function workspace(page: Page) {
  await page.addInitScript(() => sessionStorage.setItem("devpilot.access_token", "visual-test-token"));
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/me")) return route.fulfill({ json: { id: projectId, username: "Jaylan", role: "member" } });
    if (path === "/api/v1/projects") return route.fulfill({ json: { items: [project, { ...project, id: documentId, name: "团队知识空间", description: "集中整理团队文档，让每个问题都能找到可以核对的依据。" }], total: 2 } });
    if (path === `/api/v1/projects/${projectId}`) return route.fulfill({ json: project });
    if (path.endsWith("/knowledge")) return route.fulfill({ json: { mode: "mock", configured: true, ready_documents: 3 } });
    if (path.endsWith("/knowledge/questions")) return route.fulfill({ json: { mode: "mock", status: "answered", answer: "### 下单前需要确认三件事\n\n1. **配送信息**：收货人、手机号和配送地址。\n2. **商品库存**：提交前再次校验，避免超卖。\n3. **异常处理**：库存不足时保留购物车，提示调整数量。\n\n这些要求来自项目中的订单流程说明。[1]", sources: [source] } });
    if (path.endsWith("/planning")) return route.fulfill({ json: { mode: "mock", configured: true, ready_documents: 3, task_count: 2 } });
    if (path.endsWith("/planning/proposals")) return route.fulfill({ json: {
      mode: "mock", persisted: false, board_task_count: 2, sources: [source],
      tool_calls: [{ name: "search_documents", status: "success", item_count: 1 }, { name: "read_task_board", status: "success", item_count: 2 }],
      proposal: { summary: "先建立可靠的订单校验，再串联顾客下单流程。以可验证的验收标准控制交付范围。", assumptions: ["沿用现有登录与商品数据。"], risks: ["并发下单可能导致库存竞争，需要原子扣减。"], tasks: [
        { draft_id: "T1", title: "完善订单信息校验", description: "检查收货人、手机号与配送地址，给出清晰的错误提示。", priority: 1, acceptance_criteria: "信息缺失时阻止提交；补全有效信息后可继续下单。", dependencies: [], source_ids: [1] },
        { draft_id: "T2", title: "串联库存检查与下单", description: "提交前检查可售库存，保留失败时的购物车内容。", priority: 2, acceptance_criteria: "库存不足时显示原因，不产生无效订单。", dependencies: ["T1"], source_ids: [1] },
      ] },
    } });
    return route.fulfill({ status: 404, json: {} });
  });
}

test("登录页3D可暂停，减少动态后保留静态画面", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/login");
  const scene = page.getByTestId("ai-presence");
  // 本地 Chrome 支持 WebGL2：除单元测试外，再验证真实着色器与可访问控制按钮。
  await expect(scene.locator("canvas")).toHaveCSS("opacity", "1", { timeout: 10000 });
  await page.getByRole("button", { name: "暂停装饰动画", exact: true }).click();
  await expect(page.getByRole("button", { name: "播放装饰动画", exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/screenshots/redesign-login.png", fullPage: true });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(page.getByRole("button", { name: /装饰动画/ })).toHaveCount(0);
  await expect(page.getByText("已减少动态")).toBeVisible();
  expect(errors).toEqual([]);
});

test("深色项目与聊天空态，输入框在双端首屏可达", async ({ page }) => {
  await workspace(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/projects");
  await expect(page.getByRole("heading", { name: "餐厅外卖网站", exact: true })).toBeVisible();
  await page.screenshot({ path: "test-results/screenshots/redesign-projects.png", fullPage: true });
  await page.goto(`/projects/${projectId}?tab=chat`);
  const input = page.getByLabel("你想了解什么？");
  await expect(input).toBeEnabled();
  await expect(page.getByTestId("ai-presence").locator("canvas")).toHaveCSS("opacity", "1", { timeout: 10000 });
  await page.getByRole("button", { name: "暂停装饰动画", exact: true }).click();
  await page.screenshot({ path: "test-results/screenshots/redesign-chat-empty.png", fullPage: true });
  await expect(input).toBeInViewport();
  await input.fill("顾客下单之前，需要校验哪些信息？");
  await page.getByRole("button", { name: "发送问题", exact: true }).click();
  await expect(page.getByRole("heading", { name: "下单前需要确认三件事" })).toBeVisible();
  await page.screenshot({ path: "test-results/screenshots/redesign-chat-answer.png", fullPage: true });
  await page.setViewportSize({ width: 375, height: 812 });
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect(input).toBeInViewport();
  await expect(page.getByRole("button", { name: "发送问题", exact: true })).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/screenshots/redesign-chat-mobile.png", fullPage: true });
});

test("规划左右工作区与无WebGL降级不阻断业务", async ({ page }) => {
  await workspace(page);
  await page.addInitScript(() => {
    const getContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (type: string, ...args: unknown[]) {
      if (type === "webgl2") return null;
      return Reflect.apply(getContext, this, [type, ...args]);
    } as typeof getContext;
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(`/projects/${projectId}?tab=planning`);
  await expect(page.getByTestId("ai-presence-fallback")).toBeVisible();
  await expect(page.getByLabel("你想完成什么目标？")).toBeEnabled();
  await page.screenshot({ path: "test-results/screenshots/redesign-planning-empty.png", fullPage: true });
  await page.getByLabel("你想完成什么目标？").fill("完善顾客下单流程，覆盖信息校验、库存检查和异常处理。");
  await page.getByRole("button", { name: "生成任务草案", exact: true }).click();
  await expect(page.getByRole("region", { name: "任务方案预览" })).toBeVisible();
  await page.screenshot({ path: "test-results/screenshots/redesign-planning-result.png", fullPage: true });
  await expect(page.getByRole("button", { name: "重新生成草案", exact: true })).toBeInViewport();
});
