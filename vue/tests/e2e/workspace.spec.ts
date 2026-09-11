import { randomUUID } from "node:crypto";
import { test, expect, type Page } from "@playwright/test";
import type { ProjectVO, UserVO } from "../../src/types/api";

// 界面回归使用独立的接口替身，避免操作开发环境中的真实项目。
async function mockApi(page: Page, role: UserVO["role"] = "member") {
  const user: UserVO = {
    id: randomUUID(),
    username: "demo_member",
    role,
    created_at: "2026-09-10T00:00:00Z",
    updated_at: "2026-09-10T00:00:00Z",
  };
  const state = {
    projects: [] as ProjectVO[],
    expired: false,
    failList: false,
    projectRequests: 0,
  };
  await page.route("**/api/v1/**", async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    const path = url.pathname.replace("/api/v1", "");
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, json: body });
    if (path === "/auth/token") {
      const body = req.postDataJSON();
      if (body.password !== "test-password")
        return json(
          {
            error: { code: "invalid_credentials", message: "用户名或密码错误" },
          },
          401,
        );
      return json({
        access_token: "test-token",
        token_type: "bearer",
        expires_in: 1800,
        user,
      });
    }
    if (state.expired || req.headers().authorization !== "Bearer test-token")
      return json(
        { error: { message: "登录已失效", code: "invalid_credentials" } },
        401,
      );
    if (path === "/me") return json(user);
    state.projectRequests++;
    if (role !== "member")
      return json(
        { error: { message: "没有权限", code: "insufficient_permissions" } },
        403,
      );
    if (path === "/projects" && req.method() === "GET") {
      if (state.failList)
        return route.fulfill({ status: 502, body: "<html>Bad Gateway</html>" });
      const offset = Number(url.searchParams.get("offset"));
      const limit = Number(url.searchParams.get("limit"));
      return json({
        items: state.projects.slice(offset, offset + limit),
        total: state.projects.length,
        offset,
        limit,
      });
    }
    if (path === "/projects" && req.method() === "POST") {
      const qo = req.postDataJSON();
      if (state.projects.some((p) => p.name === qo.name))
        return json(
          {
            error: {
              code: "project_name_exists",
              message: "当前用户已经拥有同名项目",
            },
          },
          409,
        );
      const project: ProjectVO = {
        ...qo,
        id: randomUUID(),
        owner_id: user.id,
        created_at: "2026-09-10T00:00:00Z",
        updated_at: "2026-09-10T00:00:00Z",
      };
      state.projects.unshift(project);
      return json(project, 201);
    }
    const project = state.projects.find((p) => path === `/projects/${p.id}`);
    if (!project)
      return json(
        { error: { code: "project_not_found", message: "项目不存在" } },
        404,
      );
    if (req.method() === "PATCH") Object.assign(project, req.postDataJSON());
    if (req.method() === "DELETE") {
      state.projects = state.projects.filter((p) => p.id !== project.id);
      return route.fulfill({ status: 204 });
    }
    return json(project);
  });
  return state;
}

async function signIn(page: Page) {
  await page.goto("/login");
  await page.getByLabel("用户名", { exact: true }).fill("demo_member");
  await page.getByLabel("密码", { exact: true }).fill("test-password");
  await page.getByRole("button", { name: "登录", exact: true }).click();
}

test("登录、创建、查看、修改和删除项目", async ({ page }) => {
  await mockApi(page);
  await signIn(page);
  await expect(
    page.getByRole("heading", { name: "从你的第一个项目开始" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "新建项目", exact: true }).click();
  await page.getByLabel("项目名称").fill("餐厅外卖网站");
  await page.getByLabel("需求说明").fill("顾客在线点餐，餐厅在线接单。");
  await page.getByRole("button", { name: "创建项目", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "餐厅外卖网站", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "打开项目", exact: true }).click();
  await expect(
    page.getByText("顾客在线点餐，餐厅在线接单。", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "编辑项目", exact: true }).click();
  await page.getByLabel("需求说明").fill("还需要支持订单支付。");
  await page.getByRole("button", { name: "保存修改", exact: true }).click();
  await expect(
    page.getByText("还需要支持订单支付。", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "餐厅外卖网站" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "返回我的项目" }).click();
  await page
    .getByRole("button", { name: "删除项目：餐厅外卖网站", exact: true })
    .click();
  await page.getByRole("button", { name: "取消", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "餐厅外卖网站", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "删除项目：餐厅外卖网站", exact: true })
    .click();
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "从你的第一个项目开始" }),
  ).toBeVisible();
});

test("未登录拦截、错误密码和退出登录", async ({ page }) => {
  await mockApi(page);
  await page.goto("/projects");
  await expect(page).toHaveURL(/\/login\?redirect=/);
  await page.getByLabel("用户名", { exact: true }).fill("demo_member");
  await page.getByLabel("密码", { exact: true }).fill("wrong-password");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("用户名或密码错误");
  await page.getByLabel("密码", { exact: true }).fill("test-password");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/projects$/);
  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect
    .poll(() =>
      page.evaluate(() => sessionStorage.getItem("devpilot.access_token")),
    )
    .toBeNull();
});

test("项目失败可重试，登录过期自动退出", async ({ page }) => {
  const state = await mockApi(page);
  state.failList = true;
  await signIn(page);
  await expect(
    page.getByRole("heading", { name: "项目加载失败" }),
  ).toBeVisible();
  state.failList = false;
  await page.getByRole("button", { name: "重新加载" }).click();
  await expect(
    page.getByRole("heading", { name: "从你的第一个项目开始" }),
  ).toBeVisible();
  state.expired = true;
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(page).toHaveURL(/reason=expired/);
  await expect(
    page.getByText("登录已失效，请重新登录", { exact: true }),
  ).toBeVisible();
});

test("审批人无法进入成员项目列表", async ({ page }) => {
  const state = await mockApi(page, "reviewer");
  await signIn(page);
  await expect(page).toHaveURL(/\/reviewer$/);
  await page.goto("/projects");
  await expect(page).toHaveURL(/\/reviewer$/);
  await expect(
    page.getByRole("heading", { name: "审批中心即将开放" }),
  ).toBeVisible();
  expect(state.projectRequests).toBe(0);
});

test("分页与删除最后一页后的回退", async ({ page }) => {
  const state = await mockApi(page);
  state.projects = Array.from({ length: 10 }, (_, i) => ({
    id: randomUUID(),
    owner_id: randomUUID(),
    name: `项目${i + 1}`,
    description: "需求说明",
    created_at: "2026-09-10T00:00:00Z",
    updated_at: "2026-09-10T00:00:00Z",
  }));
  await signIn(page);
  await expect(
    page.getByRole("link", { name: "项目1", exact: true }),
  ).toBeVisible();
  await page.locator(".el-pager li").filter({ hasText: /^2$/ }).click();
  await expect(
    page.getByRole("link", { name: "项目10", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "删除项目：项目10", exact: true })
    .click();
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "项目1", exact: true }),
  ).toBeVisible();
});

test("表单校验与重名错误保留输入", async ({ page }) => {
  await mockApi(page);
  await signIn(page);
  await page.getByRole("button", { name: "新建项目", exact: true }).click();
  await page.getByLabel("项目名称").fill("   ");
  await page.getByRole("button", { name: "创建项目", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("请输入项目名称");
  await page.getByLabel("项目名称").fill("相同名称");
  await page.getByRole("button", { name: "创建项目", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "相同名称", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "新建项目", exact: true }).click();
  await page.getByLabel("项目名称").fill("相同名称");
  await page.getByLabel("需求说明").fill("不要丢失这段内容");
  await page.getByRole("button", { name: "创建项目", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
    "当前用户已经拥有同名项目",
  );
  await expect(page.getByLabel("需求说明")).toHaveValue("不要丢失这段内容");
});

test("桌面和手机布局没有横向溢出", async ({ page }) => {
  const state = await mockApi(page);
  await page.goto("/login");
  await page.screenshot({
    path: "test-results/screenshots/login-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("button", { name: "登录", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await signIn(page);
  await expect(
    page.getByRole("heading", { name: "从你的第一个项目开始" }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/screenshots/projects-mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  state.projects = ["餐厅外卖网站", "团队知识库", "个人博客"].map((name) => ({
    id: randomUUID(),
    owner_id: randomUUID(),
    name,
    description: "整理需求，记录目标，让每一步工作都有方向。",
    created_at: "2026-09-10T00:00:00Z",
    updated_at: "2026-09-10T00:00:00Z",
  }));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "餐厅外卖网站", exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "test-results/screenshots/projects-desktop.png",
    fullPage: true,
  });
});
