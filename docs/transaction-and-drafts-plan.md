# 事务可靠性与规划草案直接送审：代码方案

## 本次范围

按用户确认，完成两项：数据库事务/连接生命周期修复，以及规划草案保存、编辑、直接送审。现有未提交的部署工作保留。登录、监控、备份、多团队和聊天记忆不在本次实现范围内。

目标使用流程：

```text
输入目标 → 生成并保存草案 → 查看/编辑/保存 → 提交这一版
                                           ↓
                              原有审批流程 → 批准后创建任务
```

提交已保存草案不调用模型，不接受客户端伪造资料来源或项目身份。刷新后能打开草案，重复送审指向同一个审批会话。

## 1. 数据库事务与连接

### 1.1 普通接口

- `api/dependencies.py` 的数据库依赖明确使用函数作用域，保证路由返回后、HTTP 响应发送前提交并释放。
- 统一各控制器的数据库依赖定义，避免个别接口仍使用旧的请求作用域。
- 保留请求失败自动回滚；增加真实 ASGI 生命周期测试，模拟提交失败，验证不会先发成功响应。

### 1.2 AI 与流式接口

- RAG、规划和需求检查的长操作不再接收控制器传入的 Session，改为使用服务注入的 session factory。
- 权限检查、资料读取、结果复核各自使用短会话；模型等待、向量检索和 NDJSON 发送在数据库会话之外执行。
- 流式控制器先完成权限检查，再把不可变的用户 ID、项目 ID 与请求参数交给业务操作；不捕获仍需使用的请求级 Session。
- 鉴权依赖同样在响应前释放数据库连接，保留服务端角色检查。
- 规划读取器现有的独立短会话、并行分支隔离和资料变化检查继续使用。

涉及：`database.py`、`api/dependencies.py`、各控制器、`rag_service.py`、`plan_service.py`、`workflow_service.py`、`approval_service.py`、`main.py`。

## 2. 规划草案数据

新增 `PlanDraftDO` / `plan_drafts` 表和 Alembic 迁移：

| 字段 | 用途 |
| --- | --- |
| id | 草案 UUID |
| project_id、owner_id | 服务端确定的归属 |
| goal | 生成这一版草案时的目标 |
| plan | 校验后的 PlanResultVO，包括方案、来源、工具读取范围 |
| document_hashes | 生成时引用文档的内容指纹 |
| version | 乐观锁版本，从 1 开始，编辑后递增 |
| conversation_id | 送审后关联的唯一持久会话；为空表示未提交 |
| created_at、updated_at | 创建和最后编辑时间 |

草案状态从 conversation_id 推导为 draft/submitted。提交后禁止编辑；需要新方案时另行生成草案。version 表示内容版本，提交本身不改变内容版本，同版本重试可返回同一审批会话。

来源编号、文档片段、工具结果与模式由服务端保存，更新请求只能修改 proposal。用户不能覆盖 owner/project/document_hashes 或伪造来源正文。

## 3. 新增服务与接口

新增 `plan_draft_service.py`，复用 PlanService 生成能力及 ApprovalService 的持久审批能力。

| 接口 | 行为 |
| --- | --- |
| POST `/projects/{project_id}/planning/drafts/stream` | 生成并持久保存草案，再发送 final |
| GET `/projects/{project_id}/planning/drafts` | 当前成员的草案分页列表 |
| GET `/projects/{project_id}/planning/drafts/{id}` | 读取指定草案 |
| PATCH `/projects/{project_id}/planning/drafts/{id}` | 提交 version + proposal，保存编辑 |
| POST `/projects/{project_id}/planning/drafts/{id}/submit/stream` | 提交 version；将已保存内容交给审批，返回 ApprovalVO |

新增请求/响应结构：DraftUpdateQO、DraftSubmitQO、PlanDraftVO、PlanDraftPageVO。生成输入复用 PlanRequestQO。

关键错误：草案不存在/越权返回 404；版本冲突、已提交后编辑、资料已变化或现有任务冲突返回 409；非法引用、结构或依赖关系返回 422。版本冲突时前端保留编辑内容，不自动覆盖新版本。

## 4. 送审与中断恢复

1. 在短事务中锁定草案，检查归属与版本。
2. 对未提交草案，重新校验引用编号、文档状态/内容指纹、任务标题冲突及方案结构。
3. 在同一事务中创建 Conversation 并把 conversation_id 绑定到草案，确定唯一送审对象。
4. 事务提交后启动原有 ApprovalGraph。首次执行时，从服务端已提交草案读取 plan，直接进入保存审批与暂停节点，跳过模型生成。
5. 如果请求在绑定会话后中断，再次提交从同一会话继续；如果检查点已经存在，使用原有恢复逻辑。
6. 新提交与旧的“生成并提交”会话共存。旧审批检查点的节点名称、状态字段和决定恢复方式保持兼容。
7. 审批决定、编辑批准与任务幂等写入继续使用现有机制。

草案绑定会话后即冻结；客户端收到不确定结果时刷新记录或重试同一草案，不新建会话。模型调用计数测试必须证明送审和重复送审不会调用生成器。

## 5. 流式契约

- 增加 `draft` final kind，结果为 PlanDraftVO，生成使用规划的时间预算。
- 保留现有 node/tool 进度和 error 格式；送审继续使用 approval final。
- 同步后端 Pydantic 事件类型、前端 Results/解析器、共享 `stream.contract.json` 和生成的 API 类型。
- 只有草案事务提交成功后才能发送 final，前端据此展示“已保存”。

## 6. 前端流程

- `TaskPlanning.vue` 的“生成任务草案”改为生成并保存，保留现有来源、风险和任务展示。
- 增加草案记录列表和选中草案恢复，刷新后可重新打开。
- 增加草案编辑区：摘要、任务标题、说明、优先级和验收标准；来源与依赖保持清晰可见。
- 保存编辑使用草案版本号；冲突时保留本地内容，允许主动载入最新草案。
- “提交这一版”只提交草案 ID 和版本。存在未保存编辑时先要求保存，避免送审内容与页面不一致。
- 原“提交与审批”改为审批记录入口，取消基于当前输入目标再生成一份方案的新增入口；旧中断会话保留继续执行能力。
- 送审成功后刷新草案及审批记录，并展示同一版方案。
- 控制按钮并发、路由离开后的迟到响应、取消等待和错误提示，保持桌面内容区滚动与移动端布局。

## 7. 验证与交付标准

后端：

- 提交成功发生在 HTTP 成功响应之前；提交失败返回错误并回滚。
- 模型等待和流式发送期间，鉴权及业务读取会话已释放；取消与异常同样释放。
- 草案保存后可读取，跨用户/项目访问被拒绝。
- 正常编辑递增版本；旧版本不会覆盖，提交后不能继续编辑。
- 原始引用不可篡改；缺失文档、资料变化、同名任务与非法依赖正确拦截。
- 草案内容与审批内容一致；送审和重试的模型调用次数为零。
- 提交中断、服务重新创建及重复审批不会重复创建会话或任务。
- 旧审批流程仍通过既有恢复、回滚和幂等测试。

前端：

- 新协议解析、编辑/保存、409 冲突保留、送审与刷新恢复有单元或浏览器回归。
- 浏览器验证“生成 → 编辑 → 保存 → 提交 → 审批 → 看板”，核对文本一致且没有第二次生成请求。
- 执行生产构建，更新生成类型；在独立测试数据库验证迁移和真实事务，避免使用业务数据。

完成后更新 README 的规划操作说明，记录实际测试结果。当前任务不包含提交、推送或生产部署。

## 8. 实现与验收结果（2026-09-23）

已在 `codex/transaction-drafts` 实现本方案。未提交、推送或更新现有运行环境。

关键入口：

- `service/app/api/dependencies.py`：函数作用域事务、短会话鉴权。
- `service/app/services/plan_draft_service.py`：草案持久化、版本检查、来源复核与唯一送审绑定。
- `service/app/services/approval_service.py` / `approval_graph.py`：读取已保存方案，跳过生成节点；保留原审批恢复路径。
- `service/migrations/versions/0006_plan_drafts.py`：新增草案表，不回填旧的临时预览。
- `vue/src/components/PlanDraftList.vue` / `PlanDraftActions.vue`：打开草案、编辑保存、冲突处理与直接送审。
- `vue/src/components/TaskPlanning.vue` / `PlanningApprovals.vue`：规划工作区与审批记录衔接。

实际验证：

| 项目 | 结果 |
| --- | --- |
| 后端全量回归（包含 PostgreSQL 专项） | 295 项通过 |
| 新增草案流式提交边界专项 | 2 项通过；提交成功后才发 final，提交失败回滚并发 error |
| 取消规划后释放容量的原有断言复核 | 1 项通过（属于上述后端用例） |
| 前端单元测试 | 89 项通过 |
| 生产构建及 TypeScript 检查 | 通过 |
| 浏览器页面回归 | 59 项通过；其中 1 项修正旧文案断言后单独复测通过 |
| 真实 HTTP / 浏览器三阶段流程 | 3 项通过，API 进程重启 2 次 |
| 独立 PostgreSQL 迁移、并发版本与送审恢复 | 通过；并发编辑同一版本仅一方成功，重复送审仅一个会话 |
| 修改的 Python 文件 Ruff 检查与格式 | 通过 |

全量回归日志位于 `test-results/day13-0f67fa7d0d/`（该次浏览器汇总保留了修正前的一项文案断言失败）；修正后的单项浏览器测试已通过。最终隔离数据库及重启验收报告位于 `test-results/day13-d060a5e195/report.json`，状态为 `passed`。测试目录不进入版本控制。

真实浏览器验收还核对：成员修改的标题在刷新后仍保留，送审后审批人看到完全相同的标题，生成接口只调用一次；审核人修改批准后，任务持久保存且重试不重复写入。所有模型使用离线测试模式，未验证真实供应商延迟或可用性。测试数据库和临时索引已清理。

升级时先执行 `alembic upgrade head`，再启动新版 API 和前端；现有 Docker 启动流程已包含迁移。当前仍以单 API 实例为部署边界，同一工作流执行锁没有扩展为跨进程锁。本次没有实现任务队列、分布式执行或其它企业化扩展。

事务作用域采用 FastAPI 官方的 [yield 依赖 function scope](https://fastapi.tiangolo.com/advanced/advanced-dependencies/#dependencies-with-yield-and-scope)：依赖退出在响应发送前执行。流式业务另外使用自身短事务，避免在已经发送 HTTP 头后才尝试提交普通写接口事务。
