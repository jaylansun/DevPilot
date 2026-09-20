# 第 11 天：NDJSON 流、执行轨迹与增量显示

## 页面变化

- **AI 问答**：真实模型回答逐步出现。完成引用校验后，完整回答替换临时预览，并显示原文来源。
- **需求检查**：实时显示识别用途、检索文档、读取看板、生成报告和校验的进度。选中文档问答用途时，也显示回答文字增量。
- **任务规划**：实时显示生成草案、每次文档检索、看板读取和最终校验。报告、任务、依赖等结构化数据完整校验后再展示。
- 三处都有可展开的“执行轨迹”，事件来自真实执行位置，不用定时器模拟进度。失败、断流或取消后清除未校验的回答，保留输入和重试入口；迟到事件不能覆盖新请求。

`mock` 模式只展示真实读取进度及原有演示结果，不模拟模型打字效果。每轮仍是独立请求，历史不发送给模型。这次没有会话表、数据库迁移、审批或任务写入；持久会话、Checkpoint、审批与幂等写入在第 12 天处理。

## 接口与协议

原有 JSON 接口保留，页面改用以下 POST 接口，请求体与原接口相同，统一前缀 `/api/v1`：

| 页面 | 路径 |
| --- | --- |
| AI 问答 | `/projects/{project_id}/knowledge/questions/stream` |
| 需求检查 | `/projects/{project_id}/assistant/runs/stream` |
| 任务规划 | `/projects/{project_id}/planning/proposals/stream` |

JWT、角色、项目归属与输入校验在响应开始前完成，失败仍返回普通 HTTP 错误及统一 JSON。响应头发出后的业务错误使用流内 error 事件，不能再修改 HTTP 状态。

响应类型 `application/x-ndjson`，每行一个 JSON 对象，以换行结束。公共字段为 `version: 1`、从 1 开始递增的 `seq`、本次 `request_id`。

| type | 字段及含义 |
| --- | --- |
| `token` | `text`：回答新增文字，属于未校验预览 |
| `node` | `id`、固定 `name`、`status: started/completed/failed` |
| `tool` | 与 node 相同；每次工具调用有独立 ID，区分多次检索 |
| `final` | `kind: knowledge/planning/workflow`、对应原接口的完整 `result` |
| `error` | `status`、统一错误详情 `error`（含稳定错误码和请求编号） |

成功以一个 final 结束，失败以一个 error 结束。断线可能没有终止事件；客户端必须判定为失败。第 12 天再扩展审批事件，目前不发送 `approval_required`。

过程事件示例（还需 final 才算成功）：

```jsonl
{"version":1,"seq":1,"request_id":"example","type":"node","id":"n1","name":"answer_knowledge","status":"started"}
{"version":1,"seq":2,"request_id":"example","type":"token","text":"订单需要"}
{"version":1,"seq":3,"request_id":"example","type":"token","text":"手机号。[1]"}
```

前后端分别定义事件联合类型，共用 `stream.contract.json` 中的事件样例与步骤名进行契约测试。普通结果继续引用 OpenAPI 生成的类型。

## 实现方式

```text
权限检查 → 打开 NDJSON 连接 → 运行原有只读服务
  ├─ 节点与工具进入/退出 → node / tool
  ├─ 模型回答文字增量   → token（临时预览）
  └─ 完整格式、引用与上下文校验 → final 或 error
Vue fetch → ReadableStream → UTF-8 解码 → 按行解析 → 增量更新页面
```

- `run_stream_service.py` 为每次请求建立独立 ContextVar 事件通道和容量 32 的队列。并行节点共用本次通道，不同请求相互隔离。队列满时等待消费者，避免无限缓存。生成器关闭后取消并等待生产任务退出。
- `workflow_graph.py` 包装实际节点的进入、正常返回和异常位置。原有 State、路由、并行汇合与校验保留；`ainvoke` 的最终结果通过 final 返回。规划工具也在真正读取前后发送事件。
- 轨迹只发送代码定义的名称和状态，不发送问题、工具参数/返回值、第三方异常正文、密钥或模型思考。原文引用仍由原有业务结果返回。
- `RagModelService` 流式分支调用 LangChain `astream`，以字典 schema 解析模型逐步产生的结构化字段，发送累计 answer 相对上一份的新增文字。结束后用 Pydantic 完整校验，再验证引用和资料是否变化。没有先等待完整答案再分割文字。
- 流式模型不自动重试，避免重复发送已经显示的前缀。官方 MiMo `mimo-v2.5` / `mimo-v2.5-pro` 在该分支关闭深度思考；其他接口不添加该参数。普通 JSON 问答保持原有行为。
- 增量预览按纯文本显示并标注“正在生成，回答与引用尚未校验”。只有 final 才展示正式 Markdown 和来源。格式及引用编号正确不代表语义判断必然正确。
- 浏览器用 `TextDecoder` 保留跨包 UTF-8 字节，处理中文、emoji、半行与多行粘包。校验事件版本、序号、请求编号和最终结果类型，限制单行 100 万字符、总量 400 万字节。收到终止事件后关闭 reader。
- 沿用 JWT、401 处理和前端 75 秒超时。业务服务总预算仍为 65 秒，流通道有 70 秒保护。Nginx 关闭代理缓冲，服务端设置 `X-Accel-Buffering: no` 与禁止缓存/转换的响应头。
- 停止等待、切换标签或离开页面会断开请求；服务器收到断连后取消模型/Graph 协程并释放处理名额。同步向量线程或供应商已开始的计算不保证立即停止，不承诺退还已经产生的费用。

## 关键文件

| 文件 | 职责 |
| --- | --- |
| `service/app/schemas/stream_vo.py` | NDJSON 事件类型与校验 |
| `service/app/services/run_stream_service.py` | 事件通道、背压、取消、错误与终止 |
| `service/app/services/rag_model_service.py` | 真实回答文字增量 |
| `service/app/services/workflow_graph.py`、`service/app/tools/planning_tools.py` | 实际节点与工具轨迹 |
| `vue/src/api/stream_client.ts` | 逐行解析与事件处理 |
| `vue/src/components/RunTrace.vue` | 共用执行轨迹 |
| `vue/src/types/stream.ts`、`stream.contract.json` | 联合类型与共享契约样例 |
| `service/tests/test_streaming.py` | 实际 Graph、API、模型 SSE、ASGI 断连、背压、引用失败和只读验证 |
| `vue/tests/unit/stream_client.test.ts` | 分包、错误、超时、取消、认证与契约 |
| `vue/tests/e2e/streaming.spec.ts` | 真实 HTTP 分块响应到页面的渲染与交互 |

## 验证与部署

自动化测试使用独立 SQLite、假索引、离线模型及 SSE 替身；浏览器使用隔离数据与本地分块 HTTP 服务，不操作真实业务数据。

2026-09-20 最终验证：**256 项后端测试、65 项前端单元测试、55 项生产包浏览器测试全部通过**；生产构建、TypeScript 类型检查、新增/修改 Python 的 Ruff 检查及 `git diff --check` 通过。后端有一条已有的 Starlette/AnyIO 弃用提示，不影响测试结果。已查看桌面与手机流式页面截图。

2026-09-20 另用已配置的 MiMo v2.5 进行独立进程验收：输入合成订单规则，约 **5.73 秒**收到首段文字，**6.95 秒**完成，共 **8 个 token 事件**，最终引用校验通过。这是单次测量，不是延迟保证。没有替换运行中服务、修改环境变量或输出密钥。

本地验证：后端执行 `pytest`，前端执行 `npm test`、`npm run build`。Docker 占用默认端口时，可用 `DEVPILOT_E2E_PORT=5184 npm run test:e2e`；生产包验证用同一变量配合 `npm run test:e2e:preview`。

Jenkins 凭据及模型环境变量无需调整。合并代码后重新构建前后端镜像，才能同时启用新接口、页面与 Nginx 配置。本地开发完成不会自动触发部署。

参考：[FastAPI StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)、[LangGraph 流式能力](https://docs.langchain.com/oss/python/langgraph/streaming)。
