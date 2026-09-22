# 第 12 天：持久规划、人工审批与幂等任务写入

## 页面使用

1. 成员进入项目的“任务规划”，填写目标。原来的“生成任务草案”仍是临时预览。
2. 在结果区切换到“提交与审批”，点击“生成并提交审批”，按当前目标重新生成方案并保存。完成后显示“等待审批”，刷新页面后切换回“提交与审批”仍可查看记录、任务、假设、风险和提交时的文档依据。
3. 审批人登录后进入“审批工作区”，查看待审方案。可直接批准、修改任务标题/说明/优先级/验收标准/依赖后批准，或拒绝。
4. 批准后任务进入成员项目的待办列，来源为 AI。拒绝不会创建任务。成员刷新审批记录或重新进入任务看板查看结果。

每次提交创建一个独立规划会话，保存一个稳定的服务端 `thread_id`。这是持久审批流程，并不是把所有 AI 问答改成带历史的多轮聊天。审批人只看到已提交的方案，不能访问成员未提交的会话或普通项目接口。

## 后端执行过程

```text
创建 Conversation（固定目标、服务端 thread_id）
  → 生成并校验 PlanResultVO
  → 保存 Approval 方案快照及文档哈希
  → interrupt(approval_id)，保存 Checkpoint 并返回等待审批
  → 人工决定写入数据库
  → Command(resume=decision)
  → 再次校验权限、引用、资料状态与任务冲突
  → 确定性节点在一个事务中写入任务和执行结果
```

- `ApprovalGraph` 用官方 PostgreSQL Checkpointer 编译。`durability="sync"` 确保每个步骤的检查点保存后才进入下一步；启动应用时调用 Checkpointer 的 `setup()` 建立/升级其内部表。
- 教程原计划用 SQLite 保存 Checkpoint；实现沿用项目已有 PostgreSQL，统一使用现有数据库持久卷，避免另加 SQLite 文件与挂载。暂停和恢复仍使用相同的 `interrupt/Command` 机制，SQLite Saver 保留用于自动化测试。
- State 仅保存可序列化的目标、方案、审批编号、决定与结果。成员/项目身份、审批人和 `EventPublisher` 放在每次运行的 `ApprovalContext` 中，由服务端重新构造。
- 内部只读规划 Agent 显式使用 `checkpointer=False`，不继承外层检查点。生成中断后重新执行必要读取，确保本次读取器拥有用于校验的来源和看板数据；校验后的完整方案由外层 Graph 保存，已经保存的方案不会重新生成。
- `interrupt` 节点不在暂停前写库或发事件，避免 `Command` 恢复时重复副作用。方案保存是独立、幂等的前置节点。
- 决定先提交为 `processing`。若网络取消或进程中断，原审批人可在“待恢复执行”中使用同一决定重试；取消等待不撤销已提交的决定。
- 若生成请求恰好在“方案已保存、尚未到达暂停点”之间断开，审批请求会先恢复至暂停点，再应用决定，无需重新生成方案。检查点缺失则返回明确错误，不记录无法执行的新决定。
- 任务与 `approved` 状态、任务编号清单在同一数据库事务提交。`execution_key` 唯一，任务 ID 由执行键和草案编号确定，并具有审批编号/草案编号唯一约束。
- 即使任务已提交而 Checkpoint 尚未记录成功，重试也读取数据库中的执行结果，不重复创建任务。不同的决定或不同审批人不能覆盖已记录的决定。
- 审批时重新校验 `PlanProposalVO`、文档引用、就绪状态与内容哈希，检查当前看板的重复标题。任务依赖由草案编号转换为真实任务 UUID 并保存。Agent 的工具仍然只读，不能自行批准或写入。
- 当前沿用单 API 实例部署，同一会话使用执行锁串行运行；数据库事务和唯一约束保护最终写入。本版本不宣称支持多个 API 实例并发恢复同一 Checkpoint。

## 新接口

统一前缀 `/api/v1`：

| 方法与路径 | 用途 |
| --- | --- |
| `POST /projects/{id}/conversations` | 成员提交 `{goal}`，创建固定目标的规划会话 |
| `GET /projects/{id}/conversations` | 成员分页读取自己的规划记录 |
| `GET /conversations/{id}` | 成员读取自己的会话；审批人仅能读取已提交方案对应的会话 |
| `POST /conversations/{id}/runs/stream` | 生成/继续已有会话，等待审批；使用已保存目标，不接受模型指定身份 |
| `GET /approvals?status=pending` | 按状态分页读取方案；成员仅看到自己的，审批人看到已提交记录 |
| `GET /approvals/{id}` | 查看方案和执行结果 |
| `POST /approvals/{id}/decide/stream` | 审批人提交 `approve`、`edit_and_approve`（带完整 `proposal`）或 `reject` |

NDJSON v1 增加 `approval_required` 过程事件（完整审批快照），以及 `kind="approval"` 的 final。等待审批也是本次 HTTP 请求的正常终点，仍发送 final 后关闭连接，不让 HTTP 一直悬挂。新增固定步骤名 `submit_approval`、`apply_approval`。前后端同步更新类型与共享契约样例。

## 关键文件

- `service/app/models/approval_do.py`：会话、审批决定和执行记录。
- `service/migrations/versions/0005_approvals.py`：新表与任务审批来源/依赖字段。
- `service/app/services/approval_graph.py`：暂停和恢复后的写入路径。
- `service/app/services/approval_service.py`：权限、方案保存、决定、事务、幂等与恢复。
- `service/app/services/checkpoint_service.py`：官方 PostgreSQL Checkpointer 生命周期。
- `vue/src/components/PlanningApprovals.vue`：成员提交、恢复和记录查询。
- `vue/src/views/ReviewerView.vue`：审批中心与任务修改表单。
- `vue/src/components/ApprovalDetails.vue`：安全展示任务、风险与文档依据。

## 部署

后端新增 `langgraph-checkpoint-postgres`；SQLite Checkpointer 仅用于开发测试。运行既有迁移命令 `uv run alembic upgrade head`，再启动应用；Jenkins/容器既有启动流程会执行 Alembic。PostgreSQL Checkpoint 表由官方 saver 在应用启动时初始化。数据库账号需要现有数据库内建表权限，不需要新增环境变量或更改模型凭据。

本次开发不自动提交、推送或部署，也不把测试记录写入现有业务数据库。验收使用单独的 `day12_test` PostgreSQL 容器。

## 验证

2026-09-21 真实模式超时排查：MiMo 请求的文档和看板读取已完成，但最终草案仍在生成时撞上旧的 65 秒总时限。任务规划和审批现采用 120 秒业务预算、130 秒流式预算、140 秒浏览器等待及 145 秒代理读取等待；问答与需求检查仍保留原有较短预算。取消、模型/工具调用次数上限与审批幂等仍然生效。

修复验证：Jenkins 同配置的禁网容器中后端 272 项通过、1 项 PostgreSQL 专项测试按配置跳过；前端单元测试 69 项、流式/规划浏览器回归 13 项通过，生产包构建及 Nginx 配置检查通过。另用当前 MiMo v2.5 和相同项目目标做了一次只读验证，86.6 秒完成并校验了 10 项草案、6 个引用来源。验证在独立进程和内存检查点中运行，没有提交审批或写入任务，也没有替换运行中的应用。

恢复回归覆盖新记录以及旧版本留下的子图检查点。内部 Agent 显式不保存检查点，并使用 `durability="async"` 避免当前 LangGraph 版本继承外层 `sync` 后等待不存在的落盘任务；外层审批 Graph 仍用同步持久化。参见 [LangGraph 无状态子图](https://docs.langchain.com/oss/python/langgraph/use-subgraphs#stateless)。

本次验证结果（2026-09-21）：后端 271 项通过（包含真实 PostgreSQL 用例），前端单元测试 65 项通过；原有 55 项浏览器回归和新增 1 项真实审批流程均通过，生产构建与本次改动的 Python 静态检查通过。检查了桌面与 390px 手机审批页面。模型使用离线替身，真实模型效果仍需使用部署后的 `live` 模式验收。

测试入口：

- `service/tests/test_approvals.py`：重建服务后的恢复、批准/修改/拒绝、重复与并发请求、取消后恢复、提交后失败、权限及输入验证。
- `service/tests/test_approvals_postgres.py`：真实 PostgreSQL Checkpointer、事务回滚、恢复与幂等；仅在设置 `TEST_APPROVAL_DATABASE_URL` 且库名为 `day12_test` 时运行。
- `service/tests/approval_smoke_app.py`：浏览器验收应用，使用真实认证、API、数据库和 Checkpointer，模型和文档检索固定为离线替身。
- `vue/tests/e2e/approval_live.spec.ts`：真实 API 的提交、刷新、修改批准和看板更新；通过 `DEVPILOT_APPROVAL_API` 指向上述独立服务，未配置时跳过。

复现 PostgreSQL 和浏览器验收（在项目根目录创建临时数据库）：

```bash
docker run --detach --rm --name devpilot-day12-test \
  --env POSTGRES_PASSWORD=day12-isolated-test --env POSTGRES_DB=day12_test \
  --publish 127.0.0.1:54329:5432 --tmpfs /var/lib/postgresql/data \
  pgvector/pgvector:pg17
```

等待容器内 `pg_isready -U postgres -d day12_test` 成功后，在后端目录执行：

```bash
cd service
export TEST_APPROVAL_DATABASE_URL='postgresql+psycopg://postgres:day12-isolated-test@127.0.0.1:54329/day12_test'
export DATABASE_URL="$TEST_APPROVAL_DATABASE_URL"
export AI_MODE=mock
export JWT_SECRET=devpilot-isolated-test-secret-32-characters
uv sync --frozen
uv run alembic upgrade head
uv run pytest -q tests/test_approvals.py tests/test_approvals_postgres.py
PYTHONPATH=. uv run uvicorn approval_smoke_app:app --app-dir tests --host 127.0.0.1 --port 5187
```

另一个终端在前端目录执行：

```bash
cd vue
DEVPILOT_APPROVAL_API=http://127.0.0.1:5187 DEVPILOT_E2E_PORT=5184 \
  npm run test:e2e:preview -- tests/e2e/approval_live.spec.ts --workers=1
```

验收应用仅接受库名 `day12_test`，会重建固定的测试项目，并创建专用测试账号；不应连接业务数据库。结束后停止验收应用，再运行 `docker stop devpilot-day12-test` 删除临时数据库。所有模型调用使用离线替身，未使用真实模型凭据。

第 13 天已补齐更广泛的故障与全流程测试，见 [测试与故障验证](day13-testing.md)。第 14 天将整理部署、演示数据和完整演示脚本。

参考：[LangGraph Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)、[持久化](https://docs.langchain.com/oss/python/langgraph/persistence)。
