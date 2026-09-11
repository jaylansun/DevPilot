import { randomUUID } from "node:crypto";
import { test, expect, type Page } from "@playwright/test";
import type { TaskStatus, TaskVO } from "../../src/types/api";

// 使用独立测试数据模拟接口，不触碰开发环境中的账号与项目。
async function taskWorkspace(page: Page) {
  const project = {
    id: randomUUID(),
    owner_id: randomUUID(),
    name: "餐厅外卖网站",
    description: "顾客在线点餐，餐厅在线接单。",
    created_at: "2026-09-11T00:00:00Z",
    updated_at: "2026-09-11T00:00:00Z",
  };
  const state = {
    tasks: [] as TaskVO[],
    patches: [] as Record<string, unknown>[],
    failedColumn: "" as TaskStatus | "",
    failPatch: false,
    expired: false,
  };
  const add = (title: string, status: TaskStatus = "todo", priority = 3) => {
    const task: TaskVO = {
      id: randomUUID(),
      project_id: project.id,
      title,
      status,
      priority,
      description: "描述具体的工作内容",
      acceptance_criteria: "关键操作均可正常完成",
      source: "manual",
      version: 1,
      created_at: project.created_at,
      updated_at: project.updated_at,
    };
    state.tasks.push(task);
    return task;
  };
  await page.addInitScript(() =>
    sessionStorage.setItem("devpilot.access_token", "task-test-token"),
  );
  await page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname.replace("/api/v1", "");
    const fail = (code: string, message: string, status: number) =>
      route.fulfill({ status, json: { error: { code, message } } });
    if (state.expired)
      return fail("invalid_credentials", "登录已失效，请重新登录", 401);
    if (req.headers().authorization !== "Bearer task-test-token")
      return fail("invalid_credentials", "没有登录", 401);
    if (path === "/me")
      return route.fulfill({
        json: {
          id: project.owner_id,
          username: "测试成员",
          role: "member",
          created_at: project.created_at,
          updated_at: project.updated_at,
        },
      });
    if (path === `/projects/${project.id}`)
      return route.fulfill({ json: project });
    const base = `/projects/${project.id}/tasks`;
    if (path === base && req.method() === "GET") {
      const status = url.searchParams.get("status");
      if (state.failedColumn === status)
        return fail("internal_error", "任务列表暂时不可用", 503);
      const priority = Number(url.searchParams.get("priority"));
      const items = state.tasks.filter(
        (task) =>
          (!status || task.status === status) &&
          (!priority || task.priority === priority),
      );
      const offset = Number(url.searchParams.get("offset"));
      const limit = Number(url.searchParams.get("limit"));
      return route.fulfill({
        json: {
          items: items.slice(offset, offset + limit),
          total: items.length,
          offset,
          limit,
        },
      });
    }
    if (path === base && req.method() === "POST") {
      const qo = req.postDataJSON();
      if (state.tasks.some((task) => task.title === qo.title))
        return fail("task_title_exists", "当前项目已经存在同标题任务", 409);
      const task = add(qo.title, qo.status, qo.priority);
      Object.assign(task, qo);
      return route.fulfill({ status: 201, json: task });
    }
    const task = state.tasks.find((task) => path === `${base}/${task.id}`);
    if (!task)
      return fail("task_or_project_not_found", "项目或任务不存在", 404);
    if (req.method() === "PATCH") {
      const qo = req.postDataJSON();
      state.patches.push(qo);
      if (state.failPatch) return route.abort("failed");
      if (qo.version !== task.version)
        return fail(
          "task_version_conflict",
          "任务已经被其他请求修改，请刷新后重试",
          409,
        );
      if (
        state.tasks.some(
          (other) => other.id !== task.id && other.title === qo.title,
        )
      )
        return fail("task_title_exists", "当前项目已经存在同标题任务", 409);
      Object.assign(task, qo, { version: task.version + 1 });
    }
    if (req.method() === "DELETE") {
      state.tasks = state.tasks.filter((other) => other.id !== task.id);
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({ json: task });
  });
  async function open() {
    await page.goto(`/projects/${project.id}?tab=tasks`);
    await expect(
      page.getByRole("heading", { name: project.name }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: "刷新任务看板" }),
    ).toBeEnabled();
  }
  return { state, add, open, project };
}
const column = (page: Page, label: string) =>
  page.getByRole("region", { name: `${label}任务`, exact: true });
const card = (page: Page, title: string) =>
  page.getByRole("article", { name: title, exact: true });

test("任务完整增删改查、验收标准与状态流转", async ({ page }) => {
  const { state, open } = await taskWorkspace(page);
  await open();
  await page.getByRole("button", { name: "新建任务", exact: true }).click();
  await page.getByLabel("任务标题").fill("完成购物车");
  await page
    .getByLabel("任务说明", { exact: true })
    .fill("支持添加商品与修改数量");
  await page.getByLabel("验收标准").fill("合计金额正确");
  await page.getByLabel("优先级", { exact: true }).selectOption("1");
  await page.getByRole("button", { name: "创建任务", exact: true }).click();
  await expect(
    column(page, "待办").getByRole("article", { name: "完成购物车" }),
  ).toBeVisible();
  await card(page, "完成购物车").getByText("查看验收标准").click();
  await expect(card(page, "完成购物车")).toContainText("合计金额正确");
  await page
    .getByRole("button", { name: "编辑任务 完成购物车", exact: true })
    .click();
  await expect(page.getByLabel("任务标题")).toHaveValue("完成购物车");
  await page.getByLabel("任务说明", { exact: true }).fill("增加清空购物车功能");
  await page.getByRole("button", { name: "保存任务" }).click();
  await expect(card(page, "完成购物车")).toContainText("增加清空购物车功能");
  expect(state.patches[0]).toEqual({
    version: 1,
    description: "增加清空购物车功能",
  });
  await page
    .getByLabel("修改任务 完成购物车 的状态")
    .selectOption("in_progress");
  await expect(
    column(page, "进行中").getByRole("article", { name: "完成购物车" }),
  ).toBeVisible();
  await page.getByLabel("修改任务 完成购物车 的状态").selectOption("done");
  await expect(
    column(page, "已完成").getByRole("article", { name: "完成购物车" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    column(page, "已完成").getByRole("article", { name: "完成购物车" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "删除任务 完成购物车" }).click();
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(card(page, "完成购物车")).toBeVisible();
  await page.getByRole("button", { name: "删除任务 完成购物车" }).click();
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(card(page, "完成购物车")).toHaveCount(0);
  expect(state.tasks).toHaveLength(0);
  await page.getByRole("link", { name: "项目概览", exact: true }).click();
  await expect(
    page.getByText("顾客在线点餐，餐厅在线接单。", { exact: true }),
  ).toBeVisible();
});

test("三列独立分页、状态和优先级筛选及新建默认值", async ({ page }) => {
  const { add, open } = await taskWorkspace(page);
  for (let i = 1; i <= 11; i++) add(`待办事项${i}`, "todo", i === 1 ? 1 : 3);
  add("正在编写接口", "in_progress", 1);
  add("完成数据库设计", "done", 2);
  await open();
  await expect(column(page, "待办").getByRole("article")).toHaveCount(8);
  await column(page, "待办")
    .getByRole("button", { name: /加载更多/ })
    .click();
  await expect(column(page, "待办").getByRole("article")).toHaveCount(11);
  await page
    .getByLabel("状态筛选", { exact: true })
    .selectOption("in_progress");
  await page.getByLabel("优先级筛选", { exact: true }).selectOption("1");
  await expect(page.getByTestId("task-column")).toHaveCount(1);
  await expect(card(page, "正在编写接口")).toBeVisible();
  await page.getByRole("button", { name: "新建任务", exact: true }).click();
  await expect(page.getByLabel("任务状态", { exact: true })).toHaveValue(
    "in_progress",
  );
  await expect(page.getByLabel("优先级", { exact: true })).toHaveValue("1");
  await page.getByLabel("任务标题").fill("其他优先级任务");
  await page.getByLabel("优先级", { exact: true }).selectOption("3");
  await page.getByRole("button", { name: "创建任务", exact: true }).click();
  await expect(
    page
      .getByRole("region", { name: "任务看板", exact: true })
      .getByRole("alert"),
  ).toContainText("不符合当前筛选条件");
  await expect(card(page, "其他优先级任务")).toHaveCount(0);
  await page.getByRole("button", { name: "清除筛选" }).click();
  await expect(card(page, "其他优先级任务")).toBeVisible();
  await expect(page.getByTestId("task-column")).toHaveCount(3);
});

test("空白标题与重复标题错误保留草稿", async ({ page }) => {
  const { add, open } = await taskWorkspace(page);
  add("已经存在的任务");
  await open();
  await page.getByRole("button", { name: "新建任务", exact: true }).click();
  await page.getByLabel("任务标题").fill("  ");
  await page.getByRole("button", { name: "创建任务", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
    "请输入任务标题",
  );
  await page.getByLabel("任务标题").fill("已经存在的任务");
  await page.getByLabel("任务说明", { exact: true }).fill("保留这份草稿");
  await page.getByRole("button", { name: "创建任务", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
    "当前项目已经存在同标题任务",
  );
  await expect(page.getByLabel("任务说明", { exact: true })).toHaveValue(
    "保留这份草稿",
  );
  await page.getByLabel("任务标题").fill("新任务");
  await page.getByRole("button", { name: "创建任务", exact: true }).click();
  await expect(card(page, "新任务")).toBeVisible();
});

test("版本冲突不覆盖他人修改，确认后才能重新载入", async ({ page }) => {
  const { add, open, state } = await taskWorkspace(page);
  const task = add("共同编辑的任务");
  await open();
  await page.getByRole("button", { name: "编辑任务 共同编辑的任务" }).click();
  await expect(page.getByLabel("任务标题")).toHaveValue(task.title);
  await page.getByLabel("任务说明", { exact: true }).fill("我的未保存草稿");
  task.description = "另一位用户已经修改";
  task.version = 2;
  await page.getByRole("button", { name: "保存任务" }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
    "你的草稿已保留",
  );
  await expect(page.getByLabel("任务说明", { exact: true })).toHaveValue(
    "我的未保存草稿",
  );
  await expect(page.getByRole("button", { name: "保存任务" })).toBeDisabled();
  expect(task.description).toBe("另一位用户已经修改");
  await page.getByRole("button", { name: "载入最新任务", exact: true }).click();
  await page.getByRole("button", { name: "继续保留草稿", exact: true }).click();
  await expect(page.getByLabel("任务说明", { exact: true })).toHaveValue(
    "我的未保存草稿",
  );
  await page.getByRole("button", { name: "载入最新任务", exact: true }).click();
  await page.getByRole("button", { name: "载入最新内容", exact: true }).click();
  await expect(page.getByLabel("任务说明", { exact: true })).toHaveValue(
    "另一位用户已经修改",
  );
  await page.getByLabel("验收标准").fill("双方确认的新标准");
  await page.getByRole("button", { name: "保存任务" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(state.patches.at(-1)).toEqual({
    version: 2,
    acceptance_criteria: "双方确认的新标准",
  });
  expect(task.description).toBe("另一位用户已经修改");
});

test("加载失败可重试，移动失败不会假装成功", async ({ page }) => {
  const { add, open, state } = await taskWorkspace(page);
  const task = add("状态可靠的任务");
  add("已完成事项", "done");
  state.failedColumn = "todo";
  await open();
  await expect(column(page, "待办").getByRole("alert")).toContainText(
    "任务列表暂时不可用",
  );
  await expect(card(page, "已完成事项")).toBeVisible();
  state.failedColumn = "";
  await column(page, "待办").getByRole("button", { name: "重试加载" }).click();
  await expect(card(page, task.title)).toBeVisible();
  state.failPatch = true;
  await page.getByLabel(`修改任务 ${task.title} 的状态`).selectOption("done");
  await expect(page.getByRole("alert")).toContainText("无法连接服务");
  await expect(page.getByLabel(`修改任务 ${task.title} 的状态`)).toHaveValue(
    "todo",
  );
  expect(task.status).toBe("todo");
  state.failPatch = false;
  task.version = 2;
  task.status = "in_progress";
  await page.getByLabel(`修改任务 ${task.title} 的状态`).selectOption("done");
  await expect(page.getByRole("alert")).toContainText("请确认最新内容后再操作");
  await expect(
    column(page, "进行中").getByRole("article", { name: task.title }),
  ).toBeVisible();
  expect(task.status).toBe("in_progress");
});

test("编辑过程中任务被删除时保留草稿，登录过期退出", async ({ page }) => {
  const { add, open, state } = await taskWorkspace(page);
  const task = add("即将删除的任务");
  await open();
  await page.getByRole("button", { name: `编辑任务 ${task.title}` }).click();
  await expect(page.getByLabel("任务标题")).toHaveValue(task.title);
  await page.getByLabel("任务说明", { exact: true }).fill("保留到其他任务");
  state.tasks = [];
  await page.getByRole("button", { name: "保存任务" }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
    "项目或任务不存在",
  );
  await expect(page.getByLabel("任务说明", { exact: true })).toHaveValue(
    "保留到其他任务",
  );
  await expect(page.getByRole("button", { name: "保存任务" })).toBeDisabled();
  await page.getByRole("button", { name: "取消", exact: true }).click();
  state.expired = true;
  await page.getByRole("button", { name: "刷新任务看板" }).click();
  await expect(page).toHaveURL(/\/login\?reason=expired/);
});

test("桌面与手机看板和表单布局", async ({ page }) => {
  const { add, open } = await taskWorkspace(page);
  add("完成购物车页面", "todo", 1);
  add("补充支付流程的验收标准", "todo", 2);
  add("编写订单接口", "in_progress", 1);
  add("绘制订单页面原型", "in_progress", 3);
  add("完成数据库表设计", "done", 2);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await open();
  await expect(card(page, "完成数据库表设计")).toBeVisible();
  // 不只检查元素存在，还验证打包后的动态颜色和布局确实生效。
  await expect(
    page.getByRole("button", { name: "新建任务", exact: true }),
  ).toHaveCSS("background-color", "rgb(8, 127, 115)");
  await expect(column(page, "待办").locator("header")).toHaveCSS(
    "border-top-color",
    "rgb(148, 167, 182)",
  );
  await expect(column(page, "进行中").locator("header")).toHaveCSS(
    "border-top-color",
    "rgb(215, 160, 81)",
  );
  await expect(column(page, "已完成").locator("header")).toHaveCSS(
    "border-top-color",
    "rgb(77, 165, 141)",
  );
  await expect(
    card(page, "完成购物车页面").getByText("P1 · 最高", { exact: true }),
  ).toHaveCSS("color", "rgb(179, 84, 67)");
  await expect(
    card(page, "补充支付流程的验收标准").getByText("P2 · 较高", {
      exact: true,
    }),
  ).toHaveCSS("color", "rgb(172, 128, 60)");
  await expect(
    card(page, "绘制订单页面原型").getByText("P3 · 普通", { exact: true }),
  ).toHaveCSS("color", "rgb(84, 118, 167)");
  const desktopBoxes = await page
    .getByTestId("task-column")
    .evaluateAll((elements) =>
      elements.map((element) => ({
        x: element.getBoundingClientRect().x,
        y: element.getBoundingClientRect().y,
      })),
    );
  expect(desktopBoxes[0]!.x).toBeLessThan(desktopBoxes[1]!.x);
  expect(desktopBoxes[1]!.x).toBeLessThan(desktopBoxes[2]!.x);
  expect(desktopBoxes[0]!.y).toBe(desktopBoxes[2]!.y);
  await page.screenshot({
    path: "test-results/screenshots/task-board-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  const mobileBoxes = await page
    .getByTestId("task-column")
    .evaluateAll((elements) =>
      elements.map((element) => ({
        x: element.getBoundingClientRect().x,
        y: element.getBoundingClientRect().y,
      })),
    );
  expect(mobileBoxes[0]!.x).toBe(mobileBoxes[2]!.x);
  expect(mobileBoxes[0]!.y).toBeLessThan(mobileBoxes[1]!.y);
  expect(mobileBoxes[1]!.y).toBeLessThan(mobileBoxes[2]!.y);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/screenshots/task-board-mobile.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "新建任务", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "创建任务", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("dialog")).toHaveCSS("opacity", "1");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/screenshots/task-dialog-mobile.png",
    animations: "disabled",
  });
});
