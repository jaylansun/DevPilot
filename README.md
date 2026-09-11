# DevPilot

一个用于学习 FastAPI、LangChain、LangGraph 和 Vue 的 AI 项目协作助手。

## 当前完成内容

- 第 1～4 天：后端基础、账号认证、角色权限、项目与任务管理接口；
- 第 5 天：Vue 登录、项目列表、项目详情、新建/编辑/删除项目和响应式工作区布局；
- PostgreSQL 17 + pgvector、数据库迁移、Docker Compose 和 Jenkins 测试部署。

第 6 天接入任务看板。文档上传、AI 问答、任务生成和审批功能继续按后续计划实施。

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

登录页的演示账号按钮只填写用户名，不会创建账号，也不包含默认密码。审批人登录后进入独立的审批工作区说明页，审批流程尚未接入。

令牌保存在当前标签页的 `sessionStorage`，不保存密码；页面刷新后通过 `/me` 重新确认身份。项目列表和详情每次从后端读取。登录失效时会回到登录页，临时网络失败可以重试。

## 前端代码与验证

前端使用 Vue Router 管理页面、Pinia 保存登录状态、Element Plus 构建中文表单。`src/api/*_api.ts` 封装接口，`http_client.ts` 统一处理令牌、超时和中文错误；`src/views` 是页面，`src/components` 是共用组件。

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
```

浏览器回归使用本机 Chrome，并自动在 5174 端口启动测试前端；API 替身使用独立的测试数据，不会操作真实项目。测试覆盖登录恢复、角色拦截、项目增删改查、分页、错误重试和手机布局。

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
