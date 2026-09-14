# 第 7 天：文档知识库

## 这轮实现什么

项目概览用于简短描述目标；任务看板记录要做的工作；知识库用来保存更详细的需求、业务规则与验收文档。

目前完成的是“把资料整理成可检索的知识”，不是聊天功能。第 8 天再接入带文档引用的 AI 问答。

处理流程：

上传文档 → PostgreSQL 保存原文与排队状态 → 后台拆分片段 → 本地中文模型生成向量 → Chroma 保存向量 → 状态变为“已就绪”。

接口上传返回 HTTP 202，代表已接收，不代表索引已完成。页面会每 3 秒刷新处理中状态；索引失败会保留文档供重试。

## 你如何部署、体验

1. 将本轮代码、`service/pyproject.toml`、`service/uv.lock` 和生成的前端类型一起提交并推送到 GitHub。
2. 在 Jenkins 点击构建。原有流水线会安装依赖、测试、构建并更新 API 与前端；API 启动时 Alembic 自动执行 `0004_documents` 迁移。
3. 此轮没有新增必填密钥，不需要为了默认配置重新上传 Jenkins 的 .env 凭据。
4. 打开项目，点击“知识库”，上传 `docs/examples/restaurant-requirements.md`。
5. 等待状态从“等待索引”变为“正在索引”，最后显示“已就绪”和片段数。
6. 刷新页面确认仍然存在；删除时需二次确认，待向量清理完成后文档从列表消失。

所有页面文字和自编注释为中文，页面样式继续使用 Tailwind。第三方库自己的日志可能仍为英文。

## 模型和数据在哪里

- 模型：`BAAI/bge-small-zh-v1.5`，通过 FastEmbed 使用 ONNX 在 CPU 本地运行，不需要 OpenAI 或其他大模型 API Key。
- 首次需要访问 Hugging Face 下载模型文件（约 90 MB 量级，缓存还包含配置和分词器文件）。以后复用本地缓存。
- 文档原文、文件名、内容哈希、状态和片段数保存在 PostgreSQL 的 `documents` 表。
- 分块内容、向量和来源元数据保存在 Chroma；不是写入已安装的 pgvector。
- Compose 为 API 新增 `knowledge_data:/app/data` 命名卷；模型缓存位于 `/app/data/models`，Chroma 位于 `/app/data/chroma`。
- 本地用 uv 启动后端时，默认目录为 `service/data`，已排除出 Git 和镜像构建上下文。
- Windows 的本地模型缓存和 WSL Docker 卷不是同一个目录，本地测试下载过不代表容器也有缓存。
- 普通 Jenkins 重建容器不会删除命名卷；不要执行 `docker compose down -v`，它会删除数据库等持久数据卷。

备份需要同时保存 PostgreSQL 数据和 `knowledge_data` 卷。备份向量库时应先停止 API 写入。仅保留镜像不能恢复上传的文档。

模型支持信息：[FastEmbed 官方模型列表](https://qdrant.github.io/fastembed/examples/Supported_Models/)。
分块方式：[LangChain Markdown 标题切分](https://docs.langchain.com/oss/python/integrations/splitters/markdown_header_metadata_splitter)。

## 下载失败怎么办

Jenkins 用来下载 Python 依赖的构建代理，不会自动成为 API 容器运行时的代理。

如果知识库显示“索引失败”，先在 WSL 的项目目录查看：

```bash
sudo docker compose logs --tail=100 api
```

若日志是 Hugging Face 连接失败，可在实际 .env 中配置 API 容器可达的 HTTPS_PROXY、HTTP_PROXY，以及 NO_PROXY=localhost,127.0.0.1,api,db,web，再更新 Jenkins 的 Secret file 并重新构建。`.env.example` 中有注释示例。

不要填容器内的 127.0.0.1:7897，它指向容器自己；Clash 地址必须是容器能够访问的 Windows 主机地址，且代理允许该网络访问。不要把真实 .env 提交到 GitHub，也不要通过关闭 TLS 验证来解决网络错误。

恢复网络后，在页面点击“重试”即可。健康检查成功只代表 API 可用，不代表向量模型已经下载完成。

## 限制与可靠性

- 只支持 UTF-8 / UTF-8 BOM 的 .md、.txt，单文件最多 2 MiB、单项目最多 20 个；不支持 PDF、Word、图片或压缩包。
- 原文统一换行后计算哈希；同一项目不能重复上传相同内容。
- 接口强制验证项目归属，不接受前端提供的用户 ID 作为权限依据。
- 分块先保留 Markdown 标题层级，再按中文标点拆分，片段最大 400 字符、重叠最多 60 字符。后续引用可定位到文档和片段编号。
- 只有一个 API 实例、一个 Uvicorn worker。不要加 --workers 或横向扩容；多实例需要另行设计任务抢占、租约和共享向量服务。
- 后台任务状态存在数据库。进程中断后，原来的“正在索引”会重新排队；同一片段使用稳定 ID，重试不累积重复向量。
- 文档删除返回 202，只有向量清理成功才删除数据库记录。失败时显示“删除失败”，可重试。
- 项目删除把向量清理任务和数据库删除放在同一个事务里；后台失败会保留任务并每隔至少 60 秒重试。删除后的项目不可再通过接口访问。
- 文档内容只作为资料处理，不执行其中的代码、链接或指令。
- 系统自动化测试使用假向量模型，不联网下载模型、不访问真实项目；生产代码不会回退到假向量。

## 主要文件

- `service/app/models/document_do.py`：文档数据库模型。
- `service/app/schemas/document_vo.py`：页面能看到的返回字段，不返回原文。
- `service/app/api/v1/document_controller.py`：上传、列表、重试、删除接口。
- `service/app/services/document_service.py`：权限、格式、大小、重复内容、数量检查。
- `service/app/services/document_index_service.py`：Markdown 分块、本地模型、Chroma。
- `service/app/services/document_worker_service.py`：后台处理、失败状态、重启恢复、向量清理。
- `service/app/models/vector_cleanup_do.py`：项目删除后的持久清理任务。
- `service/migrations/versions/0004_create_documents.py`：新增数据库表。
- `vue/src/components/DocumentLibrary.vue`：上传和文档列表页面。
- `vue/src/api/document_api.ts`：前端知识库接口调用。
