import { randomUUID } from "node:crypto";
import { test, expect, type Locator, type Page } from "@playwright/test";
import type { DocumentVO, ProjectVO, TaskVO } from "../../src/types/api";

type DeleteKind = "project" | "task" | "document";

// 所有接口都在浏览器测试中拦截，删除与新建验证只使用独立的内存数据。
async function dialogWorkspace(page: Page) {
  const timestamp = "2026-09-15T08:00:00Z";
  const project: ProjectVO = {
    id: randomUUID(),
    owner_id: randomUUID(),
    name: "餐厅外卖网站",
    description: "支持在线点餐与订单管理。",
    created_at: timestamp,
    updated_at: timestamp,
  };
  const task: TaskVO = {
    id: randomUUID(),
    project_id: project.id,
    title: "完成订单确认页面",
    description: "展示订单内容，确认配送地址。",
    acceptance_criteria: "能核对金额并提交订单。",
    status: "todo",
    priority: 2,
    source: "manual",
    version: 1,
    created_at: timestamp,
    updated_at: timestamp,
  };
  const document: DocumentVO = {
    id: randomUUID(),
    project_id: project.id,
    filename: "订单需求说明.md",
    size_bytes: 3200,
    status: "ready",
    chunk_count: 5,
    error_message: null,
    created_at: timestamp,
    updated_at: timestamp,
  };
  const state = {
    projects: [project],
    tasks: [task],
    documents: [document],
    deletes: [] as string[],
    creates: [] as string[],
  };
  const projectPath = `/projects/${project.id}`;
  const taskPath = `${projectPath}/tasks/${task.id}`;
  const documentPath = `${projectPath}/documents/${document.id}`;
  await page.addInitScript(() => {
    sessionStorage.setItem("devpilot.access_token", "dialog-test-token");
  });
  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace("/api/v1", "");
    const method = request.method();
    if (method === "DELETE") state.deletes.push(path);
    if (method === "POST") state.creates.push(path);
    if (path === "/me") {
      return route.fulfill({ json: {
        id: project.owner_id,
        username: "弹窗测试成员",
        role: "member",
        created_at: timestamp,
        updated_at: timestamp,
      } });
    }
    if (path === "/projects" && method === "GET") {
      const offset = Number(url.searchParams.get("offset") ?? 0);
      const limit = Number(url.searchParams.get("limit") ?? 9);
      return route.fulfill({ json: {
        items: state.projects.slice(offset, offset + limit),
        total: state.projects.length, offset, limit,
      } });
    }
    if (path === projectPath && method === "DELETE") {
      state.projects = [];
      return route.fulfill({ status: 204 });
    }
    if (path === projectPath && method === "GET") {
      return route.fulfill({ json: project });
    }
    if (path === `${projectPath}/tasks` && method === "GET") {
      const status = url.searchParams.get("status");
      const priority = Number(url.searchParams.get("priority"));
      const items = state.tasks.filter((item) =>
        (!status || item.status === status) && (!priority || item.priority === priority),
      );
      const offset = Number(url.searchParams.get("offset") ?? 0);
      const limit = Number(url.searchParams.get("limit") ?? 8);
      return route.fulfill({ json: {
        items: items.slice(offset, offset + limit), total: items.length, offset, limit,
      } });
    }
    if (path === taskPath && method === "DELETE") {
      state.tasks = [];
      return route.fulfill({ status: 204 });
    }
    if (path === taskPath && method === "GET") {
      return route.fulfill({ json: task });
    }
    if (path === `${projectPath}/documents` && method === "GET") {
      return route.fulfill({ json: {
        items: state.documents,
        total: state.documents.length,
        max_documents: 20,
        max_size_bytes: 2097152,
      } });
    }
    if (path === documentPath && method === "DELETE") {
      document.status = "deleting";
      return route.fulfill({ status: 202, json: document });
    }
    return route.fulfill({ status: 404, json: {
      error: { code: "test_route_not_found", message: "测试未定义此接口" },
    } });
  });
  return { state, project, task, document, projectPath, taskPath, documentPath };
}

async function expectCentered(page: Page, modal: Locator, maximumWidth: number) {
  await expect(modal).toBeVisible();
  await expect(modal).toHaveCSS("opacity", "1");
  await expect.poll(async () => {
    const box = await modal.boundingBox();
    if (!box) return Infinity;
    const viewport = page.viewportSize()!;
    return Math.max(
      Math.abs(box.x + box.width / 2 - viewport.width / 2),
      Math.abs(box.y + box.height / 2 - viewport.height / 2),
    );
  }).toBeLessThanOrEqual(3);
  const box = (await modal.boundingBox())!;
  const viewport = page.viewportSize()!;
  expect(box.width).toBeLessThanOrEqual(maximumWidth);
  expect(box.x).toBeGreaterThanOrEqual(15);
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width - 15);
  expect(box.y).toBeGreaterThanOrEqual(15);
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height - 15);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
}

const deletionCases: { kind: DeleteKind; label: string; width: number; height: number; screenshot: string }[] = [
  { kind: "project", label: "项目1440桌面", width: 1440, height: 900, screenshot: "delete-project-desktop-1440" },
  { kind: "project", label: "项目1920桌面", width: 1920, height: 1080, screenshot: "delete-project-desktop-1920" },
  { kind: "project", label: "项目375手机", width: 375, height: 812, screenshot: "delete-project-mobile" },
  { kind: "task", label: "任务1920桌面", width: 1920, height: 1080, screenshot: "delete-task-desktop" },
  { kind: "document", label: "文档1920桌面", width: 1920, height: 1080, screenshot: "delete-document-desktop" },
];

for (const scenario of deletionCases) {
  test(`${scenario.label}删除弹窗紧凑居中，危险按钮不默认聚焦，ESC不删除，确认仅删除一次`, async ({ page }) => {
    await page.setViewportSize({ width: scenario.width, height: scenario.height });
    await page.emulateMedia({ reducedMotion: "reduce" });
    const { state, project, task, document: documentRecord, projectPath, taskPath, documentPath } = await dialogWorkspace(page);
    const route = scenario.kind === "project" ? "/projects" :
      `${projectPath}?tab=${scenario.kind === "task" ? "tasks" : "documents"}`;
    const deleteLabel = scenario.kind === "project" ? `删除项目：${project.name}` :
      scenario.kind === "task" ? `删除任务 ${task.title}` : `删除文档 ${documentRecord.filename}`;
    const expectedPath = scenario.kind === "project" ? projectPath :
      scenario.kind === "task" ? taskPath : documentPath;
    await page.goto(route);
    await page.getByRole("button", { name: deleteLabel, exact: true }).click();
    const modal = page.locator(".el-message-box");
    const confirm = modal.getByRole("button", { name: "确认删除", exact: true });
    await expectCentered(page, modal, Math.min(480, scenario.width - 32));
    // 手机布局中，触发按钮的鼠标坐标可能落在弹窗确认按钮上；先移开再验证基色。
    await page.mouse.move(0, 0);
    expect((await modal.boundingBox())!.width).toBeGreaterThanOrEqual(Math.min(360, scenario.width - 32));
    await expect(confirm).toHaveCSS("background-color", "rgb(186, 52, 76)");
    await expect(confirm).toHaveCSS("color", "rgb(255, 255, 255)");
    await confirm.hover();
    await expect(confirm).toHaveCSS("background-color", "rgb(163, 41, 64)");
    await page.mouse.move(0, 0);
    await expect(confirm).toHaveCSS("background-color", "rgb(186, 52, 76)");
    await expect(confirm).not.toBeFocused();
    await expect.poll(() => modal.evaluate((element) => element.contains(document.activeElement))).toBe(true);
    await expect(modal.getByRole("button", { name: "取消", exact: true })).toBeInViewport({ ratio: 1 });
    await page.screenshot({ path: `test-results/screenshots/${scenario.screenshot}.png`, animations: "disabled" });
    await page.keyboard.press("Escape");
    await expect(modal).toHaveCount(0);
    expect(state.deletes).toEqual([]);
    await expect(page.getByRole("button", { name: deleteLabel, exact: true })).toBeEnabled();
    await page.getByRole("button", { name: deleteLabel, exact: true }).click();
    await confirm.click();
    await expect(modal).toHaveCount(0);
    if (scenario.kind === "document") {
      await expect(page.getByRole("article", { name: documentRecord.filename, exact: true })).toContainText("正在删除");
    } else {
      await expect(page.getByRole("button", { name: deleteLabel, exact: true })).toHaveCount(0);
    }
    expect(state.deletes).toEqual([expectedPath]);
  });
}

for (const kind of ["project", "task"] as const) {
  const label = kind === "project" ? "项目" : "任务";
  const expectedWidth = kind === "project" ? 560 : 640;
  test(`新建${label}保持表单宽度，手机不溢出，短横屏可滚动正文且页脚完整可达`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    const { state, projectPath } = await dialogWorkspace(page);
    await page.goto(kind === "project" ? "/projects" : `${projectPath}?tab=tasks`);
    await page.getByRole("button", { name: `新建${label}`, exact: true }).click();
    const modal = page.locator(".el-dialog");
    const submit = modal.getByRole("button", { name: `创建${label}`, exact: true });
    await expectCentered(page, modal, expectedWidth);
    expect((await modal.boundingBox())!.width).toBeCloseTo(expectedWidth, 0);
    await page.getByLabel(kind === "project" ? "项目名称" : "任务标题").fill(`新建${label}布局验证`);
    await page.getByLabel(kind === "project" ? "需求说明" : "任务说明", { exact: true }).fill("整理需求并核对验收条件。\n".repeat(8));
    await expect(submit).toBeInViewport({ ratio: 1 });
    await page.screenshot({ path: `test-results/screenshots/create-${kind}-desktop.png`, animations: "disabled" });
    await page.setViewportSize({ width: 375, height: 812 });
    await expectCentered(page, modal, 343);
    await expect(submit).toBeInViewport({ ratio: 1 });
    await page.screenshot({ path: `test-results/screenshots/create-${kind}-mobile.png`, animations: "disabled" });
    await page.setViewportSize({ width: 812, height: 375 });
    await expectCentered(page, modal, expectedWidth);
    await expect(submit).toBeInViewport({ ratio: 1 });
    await expect(modal.getByRole("button", { name: "取消", exact: true })).toBeInViewport({ ratio: 1 });
    expect(await modal.locator(".el-dialog__body").evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true);
    await page.screenshot({ path: `test-results/screenshots/create-${kind}-landscape.png`, animations: "disabled" });
    await modal.getByRole("button", { name: "取消", exact: true }).click();
    await expect(modal).toBeHidden();
    expect(state.creates).toEqual([]);
    expect(state.deletes).toEqual([]);
  });
}
