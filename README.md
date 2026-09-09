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

第二天将加入 Alembic、PostgreSQL 数据模型、用户与项目的持久化接口。
