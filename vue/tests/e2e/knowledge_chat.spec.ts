import { randomUUID } from "node:crypto";
import { test, expect, type Page } from "@playwright/test";

async function chat(page: Page) {
  const id = randomUUID();
  const state = {
    mode: "mock",
    configured: true,
    ready: 1,
    fail: false,
    unknown: false,
    expired: false,
    calls: 0,
    delay: 0,
  };
  await page.addInitScript(() =>
    sessionStorage.setItem("devpilot.access_token", "rag-test-token"),
  );
  await page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    if (state.expired)
      return route.fulfill({
        status: 401,
        json: { error: { code: "expired", message: "登录已失效" } },
      });
    if (path.endsWith("/me"))
      return route.fulfill({
        json: { id: randomUUID(), username: "问答测试", role: "member" },
      });
    if (path === `/api/v1/projects/${id}`)
      return route.fulfill({
        json: {
          id,
          name: "餐厅外卖网站",
          description: "在线点餐",
          created_at: "2026-09-14T00:00:00Z",
          updated_at: "2026-09-14T00:00:00Z",
        },
      });
    if (path.endsWith("/knowledge"))
      return route.fulfill({
        json: {
          mode: state.mode,
          configured: state.configured,
          ready_documents: state.ready,
        },
      });
    if (path.endsWith("/knowledge/questions")) {
      state.calls++;
      expect(req.postDataJSON().question).toBeTruthy();
      if (state.delay)
        await new Promise((resolve) => setTimeout(resolve, state.delay));
      if (state.fail)
        return route.fulfill({
          status: 502,
          json: {
            error: { code: "rag_unavailable", message: "模型服务暂时不可用" },
          },
        });
      return route.fulfill({
        json: {
          mode: state.mode,
          answer: state.unknown
            ? "当前项目文档中没有足够依据回答这个问题。"
            : "订单需要收货人、手机号和配送地址。[1]",
          status: state.unknown ? "insufficient_evidence" : "answered",
          sources: state.unknown
            ? []
            : [
                {
                  source_id: 1,
                  document_id: randomUUID(),
                  filename: "订单规则.md",
                  chunk_index: 0,
                  heading: "订单管理",
                  text: "创建订单必须填写收货人、手机号和配送地址。<img src=x onerror=alert(1)>",
                },
              ],
        },
      });
    }
    return route.fulfill({ status: 404, json: {} });
  });
  await page.goto(`/projects/${id}?tab=chat`);
  return state;
}

test("单轮问答显示来源，原文仅作文本渲染，手机布局正常", async ({ page }) => {
  await chat(page);
  await expect(
    page.getByRole("link", { name: "AI 问答", exact: true }),
  ).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("status")).toContainText("演示模式");
  await page.getByLabel("你想了解什么？").fill("下单要填写什么？");
  await page.getByRole("button", { name: "发送问题", exact: true }).click();
  await expect(
    page.getByText("订单需要收货人、手机号和配送地址。[1]", { exact: true }),
  ).toBeVisible();
  await page.locator("summary").click();
  await expect(page.locator("blockquote")).toContainText(
    "<img src=x onerror=alert(1)>",
  );
  await expect(page.locator("blockquote img")).toHaveCount(0);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "test-results/screenshots/knowledge-chat-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => window.scrollTo(0, 0));
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/screenshots/knowledge-chat-mobile.png",
    fullPage: true,
  });
  await page.reload();
  await expect(page.getByLabel("本页问答记录")).toHaveCount(0);
});

test("无资料和未配置模型不允许提问，配置恢复后可刷新", async ({ page }) => {
  const state = await chat(page);
  state.ready = 0;
  await page.getByRole("button", { name: "刷新问答状态" }).click();
  await expect(page.getByLabel("你想了解什么？")).toBeDisabled();
  await expect(
    page.getByRole("link", { name: "知识库上传资料" }),
  ).toBeVisible();
  state.ready = 1;
  state.mode = "live";
  state.configured = false;
  await page.getByRole("button", { name: "刷新问答状态" }).click();
  await expect(page.getByRole("alert")).toContainText("MODEL_NAME");
  expect(state.calls).toBe(0);
  state.configured = true;
  await page.getByRole("button", { name: "刷新问答状态" }).click();
  await expect(page.getByLabel("你想了解什么？")).toBeEnabled();
});

test("模型失败保留问题，重试成功，无依据时明确拒答", async ({ page }) => {
  const state = await chat(page);
  state.fail = true;
  await page.getByLabel("你想了解什么？").fill("库存不足能下单吗？");
  await page.getByRole("button", { name: "发送问题", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("模型服务暂时不可用");
  await expect(page.getByLabel("你想了解什么？")).toHaveValue(
    "库存不足能下单吗？",
  );
  state.fail = false;
  state.unknown = true;
  await page.getByRole("button", { name: "发送问题", exact: true }).click();
  await expect(
    page.getByText("当前项目文档中没有足够依据回答这个问题。", { exact: true }),
  ).toBeVisible();
  await expect(page.locator("summary")).toHaveCount(0);
});

test("停止等待后保留问题，登录失效跳转登录页", async ({ page }) => {
  const state = await chat(page);
  state.delay = 2000;
  await page.getByLabel("你想了解什么？").fill("订单规则是什么？");
  await page.getByRole("button", { name: "发送问题", exact: true }).click();
  await page.getByRole("button", { name: "停止等待", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("已停止等待");
  await expect(page.getByLabel("你想了解什么？")).toHaveValue(
    "订单规则是什么？",
  );
  state.expired = true;
  await page.getByRole("button", { name: "刷新问答状态" }).click();
  await expect(page).toHaveURL(/\/login\?reason=expired/);
});
