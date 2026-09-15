# DevPilot

一个用于学习 FastAPI、LangChain、LangGraph 和 Vue 的 AI 项目协作助手。

## 当前完成内容

- 第 1～4 天：后端基础、账号认证、角色权限、项目与任务管理接口；
- 第 5 天：Vue 登录、项目列表、项目详情、新建/编辑/删除项目和响应式工作区布局；
- 第 6 天：项目任务看板、任务增删改查、状态流转、优先级筛选与版本冲突处理；
- 第 7 天：文档上传、Markdown 分块、本地中文向量模型、Chroma 持久化、后台索引与失败重试；
- 第 8 天：两步知识库问答、服务端来源校验、可展开的原文引用、显式演示/真实模型模式和 12 条固定评估用例；
- 第 9 天：只读工具、带身份上下文的 Agent、结构化任务草案和独立的“任务规划”页面；
- PostgreSQL 17 + pgvector、数据库迁移、Docker Compose 和 Jenkins 测试部署。

接下来进入第 10 天的显式 LangGraph 工作流。当前仍通过页面入口区分问答与规划，暂不做意图路由；尚未接入流式输出、持久会话、草案审批或自动写入任务看板。

第 7 天的部署步骤、示例文档、模型下载和数据保存说明见 [文档知识库说明](docs/day7-knowledge-library.md)。

第 8 天的模型配置、隐私边界和评估方法见 [知识库问答说明](docs/day8-knowledge-qa.md)。默认 `AI_MODE=mock` 仅展示真实检索的来源，不调用在线模型，不伪装成已接入 AI。真实模式需要配置模型后另行验收。

第 9 天的使用方法、文件职责、工具权限和调用限制见 [任务规划说明](docs/day9-task-planning.md)。规划的 `mock` 模式用真实检索和看板读取配合固定模板展示草案；`live` 模式才由聊天模型调用工具并拆解任务。

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

Jenkins 的后端测试使用独立的假配置和禁网测试容器，不读取部署 `.env`，也不调用真实模型或连接项目数据库。测试用例使用临时数据库或模拟对象验证行为；部署阶段仍从 `devpilot-env-file` 凭据读取真实配置。因此，将部署模式改为 `AI_MODE=live` 不应改变测试条件。

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
4. 删除前会再次确认，并提示项目下的任务和文档也会删除，对应向量在后台清理。
5. 打开项目后，点击“任务看板”，新建任务并填写标题、说明、优先级和验收标准。
6. 看板按“待办 / 进行中 / 已完成”分列，卡片底部可切换状态。点击任务标题或编辑按钮查看完整内容；删除需再次确认。
7. 在“知识库”上传 .md / .txt，等待索引就绪。进入“AI 问答”，输入关于资料的问题，展开回答下方的文件名查看原文片段。
8. 进入“任务规划”，输入目标，例如“根据需求文档拆分下单功能”。生成后检查任务的优先级、验收标准、前置依赖、风险与原文引用。这里仅展示临时草案，不会在看板创建任务；刷新或离开规划页后草案会清空。

例如，“餐厅外卖网站”是项目；“完成购物车页面”“编写订单接口”是项目下的任务。“可以添加商品、修改数量，总价计算正确”是购物车任务的验收标准。

状态和优先级可以组合筛选，各列分别分页，每次加载 8 条，点击“加载更多”查看后续任务。刷新页面会保留看板入口，筛选条件恢复默认。创建和编辑不符合当前筛选条件的任务后会有提示，可以清除筛选查看。

修改任务只提交改过的字段，并携带开始编辑时的 `version`。如果期间任务被其他请求修改，后端返回 409；页面保留草稿、停止保存，点击“载入最新任务”并确认后才能重新编辑，避免直接覆盖他人的修改。卡片切换状态也使用版本检查；网络失败不会显示虚假的成功状态。

当前看板中的任务仍由成员手工创建；“任务规划”可预览拆解草案，但尚未接入审批和写入看板。也没有拖拽排序或多人实时同步。新内容可通过“刷新任务看板”重新读取。

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

浏览器回归使用本机 Chrome，并自动在 5174 端口启动测试前端；API 替身使用独立的测试数据，不会操作真实项目。测试覆盖登录恢复、角色拦截、项目与任务增删改查、分页、筛选、版本冲突、问答引用、规划草案、取消等待、错误重试和手机布局。

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
- `/api/v1/projects/{project_id}/documents`：上传、列表与索引状态；
- `DELETE /api/v1/projects/{project_id}/documents/{document_id}`：受理删除文档与对应向量；
- `POST /api/v1/projects/{project_id}/documents/{document_id}/retry`：重试失败的索引或删除；
- `GET /api/v1/projects/{project_id}/knowledge`：读取问答模式、模型配置是否齐全和就绪文档数；
- `POST /api/v1/projects/{project_id}/knowledge/questions`：单轮两步 RAG 问答，返回回答及来源片段；
- `GET /api/v1/projects/{project_id}/planning`：读取规划模式、配置状态、就绪文档数与现有任务数；
- `POST /api/v1/projects/{project_id}/planning/proposals`：按目标生成临时任务草案，不写入看板；
- `GET /api/v1/health`：服务健康检查。
