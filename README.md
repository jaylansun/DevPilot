# DevPilot

一个用于学习 FastAPI、LangChain、LangGraph 和 Vue 的 AI 项目协作助手。

## 当前完成内容

- 第 1～4 天：后端基础、账号认证、角色权限、项目与任务管理接口；
- 第 5 天：Vue 登录、项目列表、项目详情、新建/编辑/删除项目和响应式工作区布局；
- 第 6 天：项目任务看板、任务增删改查、状态流转、优先级筛选与版本冲突处理；
- PostgreSQL 17 + pgvector、数据库迁移、Docker Compose 和 Jenkins 测试部署。

接下来按第 7 天计划接入文档上传与知识库。AI 问答、任务生成和审批功能继续按后续计划实施。

## 启动

1. 确认 WSL 中的 Docker Engine 已启动。
2. 在项目根目录执行：

   ```bash
   sudo docker compose up --build
   ```

3. 打开：
   - 前端：<http://localhost:5173>
   - FastAPI 文档：<http://localhost:8000/docs>
   - 健康检查：<http://localhost:8000/api/v1/health>

## Jenkins

Jenkins 使用可选的 `ci` Profile，不会随日常开发服务自动启动：

```bash
sudo docker compose --profile ci up -d jenkins
```

打开 <http://localhost:8080>，首次解锁密码通过以下命令读取：

```bash
sudo docker compose --profile ci exec jenkins \
  cat /var/jenkins_home/secrets/initialAdminPassword
```

Jenkins 配置、插件和任务保存在 Docker 命名卷 `jenkins_home` 中，重建容器不会丢失。

## 本地不使用 Docker 的前端启动方式

```powershell
cd vue
npm ci
npm run dev
```

本地前端默认把 `/api` 转发至 `http://localhost:8000`。如使用单独的测试后端，可通过 `DEVPILOT_API_PROXY` 环境变量指定地址；容器内仍由 Nginx 转发给 `api:8000`。

## 页面使用

1. 打开前端页面，用已创建的成员账号登录。
2. 点击“新建项目”，填写项目名称和需求说明。例如：名称“餐厅外卖网站”，说明“顾客能点菜付款，餐厅能接单”。
3. 在项目卡片上点击“打开项目”查看说明，或使用编辑、删除按钮。
4. 删除前会再次确认，并提示项目下的任务也会删除。
5. 打开项目后，点击“任务看板”，新建任务并填写标题、说明、优先级和验收标准。
6. 看板按“待办 / 进行中 / 已完成”分列，卡片底部可切换状态。点击任务标题或编辑按钮查看完整内容；删除需再次确认。

例如，“餐厅外卖网站”是项目；“完成购物车页面”“编写订单接口”是项目下的任务。“可以添加商品、修改数量，总价计算正确”是购物车任务的验收标准。

状态和优先级可以组合筛选，各列分别分页，每次加载 8 条，点击“加载更多”查看后续任务。刷新页面会保留看板入口，筛选条件恢复默认。创建和编辑不符合当前筛选条件的任务后会有提示，可以清除筛选查看。

修改任务只提交改过的字段，并携带开始编辑时的 `version`。如果期间任务被其他请求修改，后端返回 409；页面保留草稿、停止保存，点击“载入最新任务”并确认后才能重新编辑，避免直接覆盖他人的修改。卡片切换状态也使用版本检查；网络失败不会显示虚假的成功状态。

当前任务由成员手工创建，尚未接入 AI 自动拆解，也没有拖拽排序或多人实时同步。新内容可通过“刷新任务看板”重新读取。

登录页的演示账号按钮只填写用户名，不会创建账号，也不包含默认密码。审批人登录后进入独立的审批工作区说明页，审批流程尚未接入。

令牌保存在当前标签页的 `sessionStorage`，不保存密码；页面刷新后通过 `/me` 重新确认身份。项目列表和详情每次从后端读取。登录失效时会回到登录页，临时网络失败可以重试。

## 前端代码与验证

前端使用 Vue Router 管理页面、Pinia 保存登录状态、Element Plus 构建中文表单，Tailwind CSS 4 负责页面布局、间距、颜色和响应式样式。`src/api/*_api.ts` 封装接口，`http_client.ts` 统一处理令牌、超时和中文错误；`src/views` 是页面，`src/components` 是共用组件。

### 样式约定

- 使用 Tailwind 工具类编写页面样式，不再新增独立的页面 CSS 文件；没有引入 UnoCSS 或 SCSS。
- `vue/src/assets/tailwind.css` 是构建入口：通过 `@theme` 统一品牌色、字体和断点，通过少量 `@apply` 公共类复用表单、弹窗和提示样式。它是 Tailwind 的配置与公共样式，不是另一套页面样式表。
- Element Plus 样式归入单独的层，项目公共样式和工具类位于其后；不引入 Tailwind Preflight，避免全局重置影响已有组件。
- 任务状态、优先级等动态颜色使用完整类名映射，不拼接 `bg-${color}` 之类的类名，否则生产构建可能漏掉样式。
- 断点为 `mobile`（680px）、`tablet`（850px）、`board`（1050px）、`desktop`（1150px）、`wide`（1550px）；例如 `grid grid-cols-3 max-board:grid-cols-1` 表示宽屏三列、小屏一列。
- 依赖与锁文件一起提交；Docker / Jenkins 使用原有 `npm ci` 和 `npm run build`，不需要安装额外的全局工具。

接口类型位于 `vue/src/types/api.generated.ts`，从本地 FastAPI OpenAPI 生成，保留后端的 QO/VO 命名。修改后端接口后，在 `vue` 目录执行：

```bash
npm run generate:api
```

生成命令需要本地安装 uv、同步后端依赖，并具备后端配置。生成文件应随代码提交，镜像构建不需要运行后端来生成类型。

在 `vue` 目录运行前端检查：

```bash
npm test
npm run build
npm run test:e2e
npm run test:e2e:preview
```

浏览器回归使用本机 Chrome，并自动在 5174 端口启动测试前端；API 替身使用独立的测试数据，不会操作真实项目。测试覆盖登录恢复、角色拦截、项目与任务增删改查、分页、筛选、版本冲突、草稿保留、错误重试和手机布局。

`test:e2e:preview` 会先生成生产包，再用相同用例测试打包后的页面；包含品牌色、优先级颜色、状态色及响应式列布局的检查，避免开发模式正常但部署后样式缺失。

任务相关代码分为：`task_api.ts` 封装接口；`use_task_board.ts` 管理分列分页、筛选和迟到请求；`task_form.ts` 构建新建与局部更新参数；`TaskBoard.vue` 展示看板；`TaskDialog.vue` 处理任务表单与编辑冲突。任务类型直接引用生成的 QO/VO，与后端字段保持一致。

前端 Dockerfile 使用 `npm ci` 按锁文件安装依赖，并在打包前运行单元测试。Jenkins 原有“构建镜像”步骤会执行这些检查，通过后继续部署。浏览器测试单独运行，需要 Chrome。

## 预置账号

项目不开放注册接口。通过容器内的管理命令创建成员或审批人账号，密码会隐藏输入：

```bash
sudo docker compose exec api \
  python -m app.cli.create_user demo_member --role member

sudo docker compose exec api \
  python -m app.cli.create_user demo_reviewer --role reviewer
```

将已有用户设置为审批人：

```bash
sudo docker compose exec api \
  python -m app.cli.set_user_role 用户名 reviewer
```

## 当前后端接口

- `POST /api/v1/auth/token`：登录并返回 Bearer JWT；
- `GET /api/v1/me`：读取当前账号；
- `/api/v1/projects`：创建、分页列表、详情、局部更新和删除项目；
- `/api/v1/projects/{project_id}/tasks`：创建、筛选、分页、局部更新和删除任务；
- `GET /api/v1/health`：服务健康检查。
