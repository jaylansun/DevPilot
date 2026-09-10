# DevPilot

一个用于学习 FastAPI、LangChain、LangGraph 和 Vue 的 AI 项目协作助手。

## 第一天完成内容

- Vue 3 + Vite 前端启动页；
- FastAPI 服务与健康检查；
- PostgreSQL 17 + pgvector 的 Docker Compose 配置；
- 本地开发配置和服务连通性检查。

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
npm install
npm run dev
```

当前已经完成实施计划第 1 至第 4 天的后端内容：Alembic 数据库迁移、用户认证、角色权限、项目与任务 CRUD、分页筛选、PATCH 版本控制、统一错误响应和 Jenkins 自动测试部署。

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
