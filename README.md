# DevPilot

DevPilot 是一个 AI 项目协作助手，将项目资料、需求分析、任务规划和人工审批连接在同一个工作区。成员可以基于知识库提问、对照现有任务检查需求缺口，并生成带优先级和验收标准的任务方案；审批人确认后，方案中的任务才会加入项目看板。

## 核心功能

| 功能 | 说明 |
| --- | --- |
| 项目与任务管理 | 管理项目、任务状态、优先级和验收标准；默认紧凑列表，支持切换三列看板、筛选和分页 |
| 项目知识库 | 上传 Markdown / TXT 文档，后台分块与向量索引，支持索引状态查看、失败重试和删除 |
| AI 问答 | 根据项目资料回答问题，附带可展开的原文引用，支持回答增量显示 |
| 需求检查 | 识别文档问答、任务查询和需求检查意图，对照文档与任务提出可能遗漏和待确认问题 |
| 任务规划 | 根据目标检索资料、读取看板，生成并保存任务草案，支持版本化编辑与直接送审 |
| 人工审批 | 保存规划会话，支持批准、修改后批准或拒绝；批准后写入任务，重复执行不会重复创建 |
| 执行进度 | 实时展示规划和检查中的节点、工具执行状态，支持取消等待和错误重试 |
| 持久化与恢复 | 保存草案、规划记录、审批决定和工作流检查点，支持中断后继续处理 |

## 使用流程

1. **准备项目**：成员创建项目，填写需求说明，维护已有任务。
2. **上传资料**：在“知识库”上传 `.md` / `.txt` 文档，等待状态变为“已就绪”。
3. **理解与检查需求**：在“AI 问答”中提问并核对引用；在“需求检查”中对照现有任务，查看可能遗漏和待确认事项。
4. **生成并修改草案**：在“任务规划”输入目标，例如“根据需求文档拆分下单功能”。生成成功后自动保存，可修改摘要、任务标题、说明、优先级和验收标准，再点击“保存修改”。刷新页面后，可从“已保存草案”重新打开。
5. **提交人工审批**：核对草案后点击“提交这一版”。系统使用已保存版本直接送审，不再调用模型；在“审批记录”中查看进度。提交后的草案不能继续修改，审批人仍可修改后批准。
6. **批准并跟踪执行**：审批人登录独立的“审批工作区”，审阅或修改方案。批准后，成员可在任务列表中查看并推进任务。

草案编辑采用版本校验；遇到冲突会保留本地编辑，需核对最新版本后再操作。重复送审同一草案会复用原会话。需求检查和规划工具只读取项目数据，保存草案不会创建看板任务。审批完成后才会写入看板；停止等待不会撤销已经保存的草案、送审绑定或审批决定，可刷新记录确认结果。

## 快速启动

需要 Python 3、Docker 和支持 `up --wait` 的 Docker Compose。后端、前端和数据库依赖均在容器内安装。从仓库根目录执行：

```bash
python3 scripts/init_env.py
docker compose -f docker-compose.yml up -d --build --wait --wait-timeout 180
docker compose -f docker-compose.yml exec api python -m app.cli.seed_demo
```

配置工具生成随机数据库密码和 JWT 密钥，并拒绝覆盖已有 `.env`。最后一步初始化示例账号、项目、任务和知识库文档，按隐藏提示设置成员与审批人密码。默认用户名为 `demo14_member` / `demo14_reviewer`，没有默认密码；也可以通过 `--member` 和 `--reviewer` 指定用户名。

| 入口 | 地址 |
| --- | --- |
| 前端 | [localhost:5173](http://localhost:5173) |
| API 文档 | [localhost:8000/docs](http://localhost:8000/docs) |
| 代理健康检查 | [localhost:5173/api/v1/health](http://localhost:5173/api/v1/health) |

首次索引需要下载中文向量模型，请等知识库文档“已就绪”后再提问。可以使用自带的[餐厅外卖网站需求文档](service/demo/restaurant.md)体验完整流程。

上述命令显式使用通用 Compose 配置，不会自动读取本机覆盖文件。已有部署应继续沿用原配置、Compose 项目名和端口。业务数据与索引保存在 `postgres_data`、`knowledge_data` 命名卷中，日常更新不要使用 `down -v`。

### 模型配置

默认 `AI_MODE=mock`，可以体验上传、真实检索、审批和任务写入，无需在线模型密钥。问答使用资料摘录，规划使用固定模板，需求检查只展示实际读取范围，不生成覆盖或遗漏结论。

要启用模型问答、任务拆解和需求检查报告，在 `.env` 中配置：

```dotenv
AI_MODE=live
MODEL_NAME=供应商提供的模型标识
LLM_API_KEY=自行填写
LLM_BASE_URL=供应商的OpenAI兼容接口地址
```

模型需要支持 Chat Completions、工具调用和项目使用的结构化输出。真实模式会将问题或目标、相关文档片段及必要的任务信息发送给配置的模型服务，回答质量需要结合项目资料评估。

更新配置后，重新创建 API 和 Web 容器：

```bash
docker compose -f docker-compose.yml up -d --force-recreate --wait --wait-timeout 180 api web
```

使用 Jenkins 部署时，更新 `devpilot-env-file` Secret file 凭据后重新构建。更换模型时需同时核对模型名称、API Key 和接口地址。

### 账号管理

项目不开放注册接口。除初始化示例数据外，也可通过管理命令创建账号，密码会隐藏输入：

```bash
docker compose -f docker-compose.yml exec api \
  python -m app.cli.create_user demo_member --role member

docker compose -f docker-compose.yml exec api \
  python -m app.cli.create_user demo_reviewer --role reviewer
```

调整已有用户的角色：

```bash
docker compose -f docker-compose.yml exec api \
  python -m app.cli.set_user_role 用户名 reviewer
```

成员管理自己的项目，审批人进入独立审批工作区，审阅已提交的方案。登录令牌保存在当前标签页的 `sessionStorage`，不保存密码；页面刷新后会重新确认身份。

## 技术栈与结构

| 层次 | 技术与职责 |
| --- | --- |
| 前端 | Vue 3、TypeScript、Vite、Vue Router、Pinia、Element Plus、Tailwind CSS 4 |
| API | Python 3.12+、FastAPI、Pydantic、SQLAlchemy 异步会话、Alembic |
| AI 编排 | LangChain 工具调用与结构化任务规划；LangGraph 意图路由、并行读取、审批暂停与恢复 |
| 知识检索 | FastEmbed 本地中文向量模型、Chroma 持久化索引 |
| 数据存储 | PostgreSQL 保存账号、项目、任务、文档原文、审批记录和工作流检查点 |
| 流式通信 | NDJSON 传输回答增量、执行进度和最终结果 |
| 部署与验证 | Docker Compose、Nginx、Jenkins、pytest、Vitest、Playwright |

浏览器通过 Nginx 访问 FastAPI。后端读取 PostgreSQL 中的业务数据，在 Chroma 中检索文档片段，并按配置调用模型服务。数据库容器使用 PostgreSQL 17 的 pgvector 镜像，当前知识库向量检索由 Chroma 承担。

```text
service/
  app/api/          API 路由与请求处理
  app/services/     检索、规划、工作流、流式事件与审批逻辑
  app/models/       数据库模型
  app/schemas/      请求与响应结构
  app/cli/          账号管理、示例数据与评估命令
  tests/            后端测试
  demo/             示例项目与需求资料
vue/
  src/views/        页面
  src/components/   共用组件
  src/api/          接口与流式响应处理
  src/types/        API 类型与流式事件契约
  tests/            前端与浏览器测试
scripts/            配置初始化与集成验收工具
docs/               功能、部署与验证文档
```

## 本地开发与验证

### 前端开发

```bash
cd vue
npm ci
npm run dev
```

开发服务器默认将 `/api` 转发到 `http://localhost:8000`，可通过 `DEVPILOT_API_PROXY` 指定其他后端。容器部署时由 Nginx 转发到 `api:8000`。

页面样式使用 Tailwind 工具类，品牌色、断点和公共样式位于 `vue/src/assets/tailwind.css`。状态与优先级颜色使用完整类名映射，避免生产构建遗漏动态拼接的样式。

接口类型由 FastAPI OpenAPI 生成。修改后端接口后，在已安装 uv、同步后端依赖并配置后端环境的情况下，进入 `vue` 目录执行 `npm run generate:api`，将生成文件随代码提交。前后端共享的流式事件契约位于 `vue/src/types/stream.contract.json`。

### 测试

在 `vue` 目录执行：

```bash
npm test
npm run build
npm run test:e2e
npm run test:e2e:preview
```

浏览器测试使用本机 Chrome；默认自动启动的测试前端占用 5174 端口，如有冲突，可使用 `DEVPILOT_E2E_PORT=5184 npm run test:e2e:preview`。常规浏览器回归使用 API 替身和独立测试数据；`test:e2e:preview` 会先构建生产包，再验证打包后的页面。

在仓库根目录验证配置初始化工具：

```bash
python3 -m unittest discover -s scripts/tests -v
```

完整集成验收需要 Docker、本地后端虚拟环境、前端依赖和 Chrome，执行：

```bash
service/.venv/bin/python scripts/test_day13.py
```

该工具创建临时 PostgreSQL 和索引目录，验证真实 API、审批、浏览器操作及进程重启后的恢复，不使用日常业务库或真实模型凭据。依赖准备和测试范围见[测试与故障验证](docs/day13-testing.md)。

### Jenkins

Jenkins 通过可选的 `ci` Profile 启动：

```bash
docker compose --profile ci up -d jenkins
docker compose --profile ci exec jenkins \
  cat /var/jenkins_home/secrets/initialAdminPassword
```

打开 [localhost:8080](http://localhost:8080)，首次使用时输入命令输出的解锁密码。配置、插件和任务保存在 `jenkins_home` 命名卷中。

流水线在隔离环境中运行后端测试，构建前端时执行单元测试与生产打包，通过后读取部署凭据并更新服务。后端测试容器禁网，不读取部署 `.env`、连接业务数据库或调用真实模型；浏览器测试需单独运行。

在仓库根目录手动运行同一后端测试镜像：

```bash
docker build --build-context stream_contract=vue/src/types \
  --target test --tag devpilot-api-test:local service
docker run --rm --network none \
  -e AI_MODE=mock \
  -e DATABASE_URL=postgresql+psycopg://test:test@127.0.0.1:1/devpilot_test \
  -e JWT_SECRET=devpilot-test-key-not-for-production \
  devpilot-api-test:local
```

命名构建上下文用于将共享流式契约加入测试镜像，普通 API 运行镜像不需要该额外上下文。

## 使用范围

- 当前支持单 API 实例；草案、规划会话与审批检查点持久化到 PostgreSQL。
- 普通写接口在发送成功响应前提交事务；AI 等待和流式传输期间，鉴权与业务查询使用的数据库连接已释放。
- 本版本新增 `0006_plan_drafts` 迁移。已有环境升级需先执行 `alembic upgrade head`；Compose/Jenkins 的启动命令会自动执行迁移。旧的只读规划 API 和审批会话仍兼容。
- 知识库支持 Markdown 和 TXT；检查结果基于实际检索到的片段，不能视为全文覆盖。有对应任务也不代表功能已经实现。
- 真实问答文字逐步显示；任务草案与检查报告先展示执行进度，通过校验后展示完整结果。
- 任务编辑使用版本检查，冲突时保留草稿并提示重新载入，避免覆盖其他修改。看板支持列表与三列视图，暂不支持拖拽排序或多人实时同步。

## 详细文档

| 主题 | 文档 |
| --- | --- |
| 部署、配置与故障定位 | [部署指南](docs/day14-deployment-demo.md) |
| 完整操作示例 | [演示脚本](docs/day14-recording-script.md) |
| 文档上传、分块与索引 | [知识库](docs/day7-knowledge-library.md) |
| 问答、引用与效果评估 | [知识库问答](docs/day8-knowledge-qa.md) |
| 工具调用与任务草案 | [任务规划](docs/day9-task-planning.md) |
| 意图路由与需求对照 | [需求检查](docs/day10-requirement-check.md) |
| 事件协议与取消处理 | [流式响应](docs/day11-streaming.md) |
| 事务与草案直接送审 | [实现方案与验证](docs/transaction-and-drafts-plan.md) |
| 持久会话与人工决策 | [规划与审批](docs/day12-approvals.md) |
| 集成验收与恢复测试 | [测试与故障验证](docs/day13-testing.md) |

完整接口、请求参数与响应结构见运行服务后的 [API 文档](http://localhost:8000/docs)。
