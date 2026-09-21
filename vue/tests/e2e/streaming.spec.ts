import { createServer, type Server, type ServerResponse } from "node:http";
import { randomUUID } from "node:crypto";
import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
const contract = JSON.parse(readFileSync(new URL("../../src/types/stream.contract.json", import.meta.url), "utf8"));

// 使用真实 HTTP 分块响应，验证浏览器在连接仍打开时就渲染增量。
let server: Server;
let origin: string;
let calls: { response: ServerResponse; seq: number; closed: boolean }[] = [];
test.beforeAll(async () => {
  server = createServer((request, response) => {
    response.setHeader("Access-Control-Allow-Origin", "*");
    response.setHeader("Access-Control-Allow-Headers", "authorization,content-type");
    if (request.method === "OPTIONS") { response.writeHead(204); response.end(); return; }
    request.resume();
    response.writeHead(200, { "Content-Type": "application/x-ndjson", "Cache-Control": "no-cache" });
    response.flushHeaders();
    const call = { response, seq: 0, closed: false };
    calls.push(call);
    response.on("close", () => { call.closed = true; });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("test server unavailable");
  origin = `http://127.0.0.1:${address.port}`;
});
test.afterAll(async () => {
  server.closeAllConnections();
  await new Promise<void>((resolve) => server.close(() => resolve()));
});
test.beforeEach(() => { calls = []; });
test.afterEach(() => { for (const call of calls) call.response.destroy(); });

function send(event: object, index = calls.length - 1) {
  const call = calls[index]!;
  call.response.write(JSON.stringify({ version: 1, seq: ++call.seq, request_id: "http-stream-test", ...event }) + "\n");
}
const result = {
  mode: "live", status: "answered", answer: "订单需要手机号。[1]",
  sources: [{ source_id: 1, document_id: randomUUID(), filename: "需求.md", chunk_index: 0, heading: "订单", text: "下单必须填写手机号。" }],
};
function finish(kind = "knowledge", value: unknown = result) {
  send({ type: "final", kind, result: value });
  calls.at(-1)!.response.end();
}

async function setup(page: Page, tab = "chat") {
  const id = randomUUID();
  await page.addInitScript(() => sessionStorage.setItem("devpilot.access_token", "offline-stream-token"));
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/stream")) return route.continue({ url: origin + path });
    if (path.endsWith("/me")) return route.fulfill({ json: { id: randomUUID(), username: "流式测试", role: "member" } });
    if (path === `/api/v1/projects/${id}`) return route.fulfill({ json: {
      id, name: "餐厅外卖网站", description: "", created_at: "2026-09-20T00:00:00Z", updated_at: "2026-09-20T00:00:00Z",
    } });
    if (/\/(knowledge|assistant|planning)$/.test(path)) return route.fulfill({ json: { mode: "live", configured: true, ready_documents: 1, task_count: 1 } });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.goto(`/projects/${id}?tab=${tab}`);
}

async function ask(page: Page) {
  await page.getByLabel("你想了解什么？").fill("订单要填什么？");
  await page.getByRole("button", { name: "发送问题", exact: true }).click();
  await expect.poll(() => calls.length).toBeGreaterThan(0);
  send({ type: "node", id: "answer", name: "answer_knowledge", status: "started" });
  send({ type: "token", text: "订单需" });
  await expect(page.getByTestId("streaming-answer")).toContainText("订单需");
}

test("真实 HTTP 增量先显示，完成后替换预览并显示引用，手机布局可用", async ({ page }) => {
  await setup(page);
  await ask(page);
  await expect(page.getByLabel("执行轨迹")).toContainText("生成回答");
  await expect(page.getByLabel("回答来源")).toHaveCount(0);
  send({ type: "token", text: "要手机号。[1]" });
  await expect(page.getByTestId("streaming-answer")).toContainText(result.answer);
  await page.screenshot({ path: "test-results/screenshots/day11-streaming-desktop.png" });
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(page.getByRole("button", { name: "停止等待", exact: true })).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "test-results/screenshots/day11-streaming-mobile.png" });
  send({ type: "node", id: "answer", name: "answer_knowledge", status: "completed" });
  finish();
  await expect(page.getByTestId("streaming-answer")).toHaveCount(0);
  await expect(page.getByLabel("回答来源")).toBeVisible();
  await page.getByLabel("回答来源").locator("summary").click();
  await expect(page.locator("blockquote")).toContainText("下单必须填写手机号");
});

test("中途错误清除未校验回答并保留请求编号和重试入口", async ({ page }) => {
  await setup(page);
  await ask(page);
  send({ type: "token", text: "<img src=x onerror=alert(1)>" });
  await expect(page.getByTestId("streaming-answer").locator("img")).toHaveCount(0);
  send({ type: "error", status: 409, error: { code: "knowledge_changed", message: "回答期间知识库发生变化", request_id: "http-stream-test", details: null } });
  calls.at(-1)!.response.end();
  await expect(page.getByTestId("streaming-answer")).toHaveCount(0);
  await expect(page.getByRole("alert")).toContainText("http-stream-test");
  await expect(page.getByRole("button", { name: "重试此问题" })).toBeEnabled();
  await expect(page.getByLabel("回答来源")).toHaveCount(0);
});

test("没有 final 的断流不能被当作成功回答", async ({ page }) => {
  await setup(page);
  await ask(page);
  calls.at(-1)!.response.end();
  await expect(page.getByRole("alert")).toContainText("流式数据不完整");
  await expect(page.getByTestId("streaming-answer")).toHaveCount(0);
});

test("停止等待会关闭连接，立即重试不被上一轮覆盖", async ({ page }) => {
  await setup(page);
  await ask(page);
  await page.getByRole("button", { name: "停止等待", exact: true }).click();
  await expect.poll(() => calls[0]!.closed).toBe(true);
  await expect(page.getByTestId("streaming-answer")).toHaveCount(0);
  await page.getByRole("button", { name: "重试此问题" }).click();
  await expect.poll(() => calls.length).toBe(2);
  send({ type: "token", text: "新的回答" });
  await expect(page.getByTestId("streaming-answer")).toContainText("新的回答");
  finish("knowledge", { ...result, answer: "新的完整回答。[1]" });
  await expect(page.getByText("新的完整回答。[1]", { exact: true })).toBeVisible();
});

for (const kind of ["planning", "workflow"] as const) {
  test(`${kind} 在最终结果到来前展示真实节点和工具轨迹`, async ({ page }) => {
    await setup(page, kind === "planning" ? "planning" : "assistant");
    if (kind === "planning") {
      await page.getByLabel("你想完成什么目标？").fill("规划下单校验");
      await page.getByRole("button", { name: "生成任务草案", exact: true }).click();
    } else await page.getByRole("button", { name: "开始检查", exact: true }).click();
    await expect.poll(() => calls.length).toBe(1);
    send({ type: "node", id: "parent", name: kind === "planning" ? "draft_proposal" : "generate_report", status: "started" });
    send({ type: "tool", id: "search", name: "search_documents", status: "started" });
    const trace = page.getByLabel("执行轨迹");
    await trace.locator("summary").click();
    await expect(trace).toContainText("检索项目文档");
    await expect(trace.getByText("进行中", { exact: true })).toHaveCount(2);
    send({ type: "tool", id: "search", name: "search_documents", status: "completed" });
    await expect(trace.getByText("已完成", { exact: true })).toHaveCount(1);
    const sample = contract.events.find((e) => e.type === "final" && "kind" in e && e.kind === kind)!;
    finish(kind, "result" in sample ? sample.result : null);
    await expect(trace).not.toContainText("进行中");
  });
}
