import { randomUUID } from "node:crypto";
import { test, expect, type Page } from "@playwright/test";
import type { DocumentVO } from "../../src/types/api";

async function library(page: Page) {
  const id = randomUUID();
  const timestamp = "2026-09-11T06:00:00Z";
  const state = {
    docs: [] as DocumentVO[],
    uploads: 0,
    failUpload: false,
    failList: false,
    expired: false,
  };
  const doc = (
    filename = "需求说明.md",
    status: DocumentVO["status"] = "queued",
  ): DocumentVO => ({
    id: randomUUID(),
    project_id: id,
    filename,
    size_bytes: 3280,
    status,
    chunk_count: status === "ready" ? 5 : 0,
    error_message: null,
    created_at: timestamp,
    updated_at: timestamp,
  });
  await page.addInitScript(() =>
    sessionStorage.setItem("devpilot.access_token", "document-test-token"),
  );
  await page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const path = new URL(req.url()).pathname;
    const fail = (message: string, status: number) =>
      route.fulfill({
        status,
        json: { error: { code: "test_error", message } },
      });
    if (state.expired) return fail("登录已失效", 401);
    if (path.endsWith("/me"))
      return route.fulfill({
        json: {
          id: randomUUID(),
          username: "知识库测试成员",
          role: "member",
          created_at: timestamp,
          updated_at: timestamp,
        },
      });
    if (path === `/api/v1/projects/${id}`)
      return route.fulfill({
        json: {
          id,
          owner_id: randomUUID(),
          name: "餐厅外卖网站",
          description: "支持在线点餐",
          created_at: timestamp,
          updated_at: timestamp,
        },
      });
    if (path.endsWith("/documents") && req.method() === "GET") {
      if (state.failList) return fail("文档列表暂时不可用", 503);
      return route.fulfill({
        json: {
          items: state.docs,
          total: state.docs.length,
          max_documents: 20,
          max_size_bytes: 2097152,
        },
      });
    }
    if (path.endsWith("/documents") && req.method() === "POST") {
      state.uploads++;
      if (state.failUpload) return fail("当前项目已上传相同内容", 409);
      expect(req.headers()["content-type"]).toContain(
        "multipart/form-data; boundary=",
      );
      const record = doc();
      state.docs.push(record);
      return route.fulfill({ status: 202, json: record });
    }
    const record = state.docs.find((item) => path.includes(item.id));
    if (!record) return fail("文档不存在", 404);
    record.status =
      req.method() === "DELETE" || record.status === "delete_failed"
        ? "deleting"
        : "queued";
    return route.fulfill({ status: 202, json: record });
  });
  const open = () => page.goto(`/projects/${id}?tab=documents`);
  return { state, doc, open };
}
const card = (page: Page, name = "需求说明.md") =>
  page.getByRole("article", { name, exact: true });

test("知识库上传、状态轮询、刷新保留与删除确认", async ({ page }) => {
  const { state, open } = await library(page);
  await open();
  await expect(page.getByText("还没有项目文档", { exact: true })).toBeVisible();
  await page
    .getByLabel("选择知识库文档")
    .setInputFiles({
      name: "需求说明.md",
      mimeType: "text/markdown",
      buffer: Buffer.from("# 需求\n支持点餐"),
    });
  await page.getByRole("button", { name: "上传文档", exact: true }).click();
  await expect(card(page)).toContainText("等待索引");
  state.docs[0]!.status = "ready";
  state.docs[0]!.chunk_count = 5;
  await expect(card(page)).toContainText("已就绪", { timeout: 8000 });
  await expect(card(page)).toContainText("5 个片段");
  await page.reload();
  await expect(card(page)).toContainText("已就绪");
  await page.getByRole("button", { name: "删除文档 需求说明.md" }).click();
  await page.getByRole("button", { name: "取消", exact: true }).click();
  expect(state.docs).toHaveLength(1);
  await page.getByRole("button", { name: "删除文档 需求说明.md" }).click();
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(card(page)).toContainText("正在删除");
  state.docs = [];
  await expect(card(page)).toHaveCount(0, { timeout: 8000 });
});

test("格式和大小校验、上传失败保留文件、列表加载失败可重试", async ({
  page,
}) => {
  const { state, open } = await library(page);
  await open();
  await page
    .getByLabel("选择知识库文档")
    .setInputFiles({
      name: "图片.png",
      mimeType: "image/png",
      buffer: Buffer.from("data"),
    });
  await page.getByRole("button", { name: "上传文档", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("仅支持");
  expect(state.uploads).toBe(0);
  await page
    .getByLabel("选择知识库文档")
    .setInputFiles({
      name: "big.txt",
      mimeType: "text/plain",
      buffer: Buffer.alloc(2097153, "a"),
    });
  await page.getByRole("button", { name: "上传文档", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("2 MB");
  expect(state.uploads).toBe(0);
  await page
    .getByLabel("选择知识库文档")
    .setInputFiles({
      name: "需求说明.md",
      mimeType: "text/plain",
      buffer: Buffer.from("需求"),
    });
  state.failUpload = true;
  await page.getByRole("button", { name: "上传文档", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("已上传相同内容");
  await expect(page.getByLabel("选择知识库文档")).not.toHaveValue("");
  state.failUpload = false;
  await page.getByRole("button", { name: "上传文档", exact: true }).click();
  await expect(card(page)).toBeVisible();
  state.failList = true;
  await page.getByRole("button", { name: "刷新知识库" }).click();
  await expect(
    page.getByRole("region", { name: "项目知识库" }).getByRole("alert"),
  ).toContainText("文档列表暂时不可用");
  state.failList = false;
  await page.getByRole("button", { name: "重新加载列表" }).click();
  await expect(
    page.getByRole("region", { name: "项目知识库" }).getByRole("alert"),
  ).toHaveCount(0);
});

test("索引和删除失败可重试，手机布局不溢出", async ({ page }) => {
  const { state, doc, open } = await library(page);
  const record = doc("需求说明.md", "failed");
  record.error_message = "索引失败，请检查网络后重试";
  state.docs.push(record);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await open();
  await expect(card(page)).toContainText("索引失败");
  await page.getByRole("button", { name: "重试文档 需求说明.md" }).click();
  await expect(card(page)).toContainText("等待索引");
  record.status = "delete_failed";
  record.error_message = "向量清理失败，请重试删除";
  await page.getByRole("button", { name: "刷新知识库" }).click();
  await expect(card(page)).toContainText("删除失败");
  await page.getByRole("button", { name: "重试文档 需求说明.md" }).click();
  await expect(card(page)).toContainText("正在删除");
  state.docs.push(doc("产品规则.txt", "ready"));
  state.docs.push(doc("验收标准.md", "indexing"));
  await page.getByRole("button", { name: "刷新知识库" }).click();
  await expect(card(page, "产品规则.txt")).toBeVisible();
  await page.screenshot({
    path: "test-results/screenshots/documents-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(card(page)).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/screenshots/documents-mobile.png",
    fullPage: true,
  });
  state.expired = true;
  await page.getByRole("button", { name: "刷新知识库" }).click();
  await expect(page).toHaveURL(/\/login\?reason=expired/);
});
