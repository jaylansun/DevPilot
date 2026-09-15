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
    hold: null as Promise<void> | null,
    answer: null as string | null,
    questions: [] as string[],
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
      const payload = req.postDataJSON();
      expect(payload).toEqual({ question: expect.any(String) });
      expect(payload.question).toBeTruthy();
      state.questions.push(payload.question);
      if (state.hold) await state.hold;
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
          answer: state.answer ?? (state.unknown
            ? "当前项目文档中没有足够依据回答这个问题。"
            : "订单需要收货人、手机号和配送地址。[1]"),
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
  await page.setViewportSize({ width: 375, height: 812 });
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
  await page.getByRole("button", { name: "重试此问题", exact: true }).click();
  await expect(
    page.getByText("当前项目文档中没有足够依据回答这个问题。", { exact: true }),
  ).toBeVisible();
  await expect(page.locator("summary")).toHaveCount(0);
  await expect(page.getByRole("log").getByRole("article")).toHaveCount(1);
  expect(state.questions).toEqual(["库存不足能下单吗？", "库存不足能下单吗？"]);
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

test("推荐问题仅填入草稿，中文组合输入不误送，Enter 发送且可清空临时记录", async ({ page }) => {
  const state = await chat(page);
  const input = page.getByLabel("你想了解什么？");
  await page.getByRole("button", { name: /梳理项目/ }).click();
  await expect(input).toHaveValue("项目资料中描述了哪些核心功能？");
  await expect(input).toBeFocused();
  expect(state.calls).toBe(0);
  await input.fill("订单规则");
  await input.dispatchEvent("compositionstart");
  await input.dispatchEvent("keydown", { key: "Enter", isComposing: true });
  expect(state.calls).toBe(0);
  await input.dispatchEvent("compositionend");
  await input.dispatchEvent("keydown", { key: "Enter", keyCode: 229 });
  expect(state.calls).toBe(0);
  await input.press("Shift+Enter");
  await expect(input).toHaveValue("订单规则\n");
  expect(state.calls).toBe(0);
  await input.press("Enter");
  await expect(page.getByText("订单需要收货人、手机号和配送地址。[1]", { exact: true })).toBeVisible();
  expect(state.questions).toEqual(["订单规则"]);
  await page.getByRole("button", { name: "清空记录", exact: true }).click();
  await expect(page.getByLabel("本页问答记录")).toHaveCount(0);
  await expect(page.getByLabel("推荐问题")).toBeVisible();
  await expect(input).toBeFocused();
});

test("长回答在消息区域滚动，375px 输入框可达，回答中的 HTML 不执行", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const state = await chat(page);
  state.answer = "## 订单说明\n\n" + "需要核对业务规则与资料来源。\n\n".repeat(35) +
    "<img src=x onerror=alert(1)>\n\n[不安全链接](javascript:alert(1))";
  await page.getByLabel("你想了解什么？").fill("解释订单规则");
  await page.getByRole("button", { name: "发送问题", exact: true }).click();
  await expect(page.getByRole("heading", { name: "订单说明", exact: true })).toHaveCount(1);
  await expect(page.getByRole("log").locator("img")).toHaveCount(0);
  await expect(page.getByRole("log").locator('a[href^="javascript:"]')).toHaveCount(0);
  expect(await page.getByTestId("chat-scroll-region").evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true);
  await page.evaluate(() => window.scrollTo(0, 0));
  await expect(page.getByRole("button", { name: "发送问题", exact: true })).toBeInViewport();
  await expect(page.getByLabel("你想了解什么？")).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("输入框随长草稿增长且不超过140px，删除文字后收起", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  const state = await chat(page);
  const input = page.getByLabel("你想了解什么？");
  await expect(input).toBeEnabled();
  const initialHeight = await input.evaluate((element) => element.getBoundingClientRect().height);
  await input.fill("需要进一步确认订单的业务规则与处理限制。\n".repeat(12));
  await expect.poll(() => input.evaluate((element) => element.getBoundingClientRect().height)).toBeGreaterThan(initialHeight);
  expect(await input.evaluate((element) => element.getBoundingClientRect().height)).toBeLessThanOrEqual(140);
  expect(await input.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true);
  await expect(page.getByRole("button", { name: "发送问题", exact: true })).toBeInViewport();
  await input.fill("短问题");
  await expect.poll(() => input.evaluate((element) => element.getBoundingClientRect().height)).toBe(initialHeight);
  await expect(input).toHaveAttribute("maxlength", "2000");
  expect(state.calls).toBe(0);
});

test("阅读历史时保留滚动位置，回到最新可继续提问，减少动态模式下同样可用", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const state = await chat(page);
  const input = page.getByLabel("你想了解什么？");
  const viewport = page.getByTestId("chat-scroll-region");
  state.answer = "## 第一份资料\n\n" + "订单资料需要核对功能、业务规则和原文引用。\n\n".repeat(24);
  await input.fill("梳理第一份资料");
  await page.getByRole("button", { name: "发送问题", exact: true }).click();
  await expect(page.getByRole("heading", { name: "第一份资料", exact: true })).toHaveCount(1);
  await expect(input).toBeEnabled();
  let releaseAnswer!: () => void;
  state.hold = new Promise<void>((resolve) => { releaseAnswer = resolve; });
  state.answer = "## 第二份资料\n\n" + "这是一份需要与前文对照的新资料。\n\n".repeat(24);
  await input.fill("再梳理第二份资料");
  await page.getByRole("button", { name: "发送问题", exact: true }).click();
  await expect(page.getByRole("button", { name: "停止等待", exact: true })).toBeVisible();
  await expect.poll(() => state.calls).toBe(2);
  await viewport.evaluate((element) => {
    element.scrollTop = 0;
    element.dispatchEvent(new Event("scroll"));
  });
  await expect(page.getByRole("button", { name: "回到最新", exact: true })).toBeVisible();
  releaseAnswer();
  await expect(page.getByRole("heading", { name: "第二份资料", exact: true })).toHaveCount(1);
  await expect(input).toBeEnabled();
  await expect.poll(() => viewport.evaluate((element) => element.scrollTop)).toBeLessThan(10);
  await expect(page.getByRole("button", { name: "回到最新", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "回到最新", exact: true }).click();
  await expect.poll(() => viewport.evaluate((element) => element.scrollHeight - element.clientHeight - element.scrollTop)).toBeLessThan(64);
  await expect(input).toBeFocused();
  await expect(page.getByRole("button", { name: "回到最新", exact: true })).toHaveCount(0);
});
