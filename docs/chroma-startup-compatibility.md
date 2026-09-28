# Chroma 在 Linux x86 虚拟机中的初始化兼容

## 故障与定位

2026-09-28 的 Jenkins #37 已完成基础镜像解析与测试镜像构建，随后在
`test_chroma_persists_isolates_projects_and_retry_is_idempotent` 的独立读取进程中超过 30 秒。
316 项测试通过，1 项失败、2 项按配置跳过；后续部署因此未执行。

在相同 Python 3.12 测试镜像、OrbStack Linux amd64 环境中禁网复现：

- 不创建客户端、不读取索引，仅导入 `chromadb_rust_bindings` 也可能卡住。
- 写入进程退出后再读取仍能复现，不能将此故障归因为索引文件锁。
- GDB 显示动态库初始化期间反复执行 `clock_gettime` 与 `RDTSC`，尚未进入集合读取。
- Chroma 1.5.9 的 [Rust 锁文件](https://github.com/chroma-core/chroma/blob/1.5.9/Cargo.lock)
  包含 fastant 0.1.11。其 [TSC 校准实现](https://docs.rs/crate/fastant/0.1.11/source/src/tsc_now.rs)
  在加载时重复比较时钟采样，直到频率差达到阈值，循环没有总时限。

临时将导入线程限制到一个可用 CPU 后，10 次独立进程导入均在约 0.03～0.09 秒完成；
未限制的对照仍出现超时。结果支持跨核采样干扰该虚拟机中的时钟校准，不代表所有宿主机都会触发。

## 兼容处理及边界

`service/app/services/chroma_compat.py` 在 Linux x86/x86_64 上读取当前线程原有的 CPU
亲和性，只在首次导入 Chroma 原生模块时暂时选择一个已允许的 CPU，并在 `finally` 中恢复。
原生模块加载完毕后才创建客户端、索引和向量计算线程，后续工作仍可使用原有 CPU 范围。

- macOS、Windows、Linux ARM 使用常规导入。
- 不修改 OrbStack、宿主机或容器整体的 CPU 配置，不更改向量数据格式。
- 容器若禁止调整亲和性，会记录警告并使用依赖原有的加载行为；此环境下无法保证规避校准超时。
- 依赖加载失败仍向上传播；测试继续检查真实落盘数据、项目隔离、幂等删除和亲和性恢复。
- 原有 30 秒子进程超时保留，25 秒时输出调用栈帮助定位，不增加测试失败自动重试。

这是当前依赖的兼容措施。升级 Chroma 后，应检查内嵌 fastant 是否已修复有界校准，
并在相同虚拟机下验证多次全新进程启动，再决定是否移除。

## 修复验证

在 Jenkins 使用的 Python 3.12 测试镜像中挂载修改后的应用与测试目录，禁网验证：
相关 10 项测试通过；完整后端测试 322 项通过、2 项按配置跳过，耗时 57.92 秒。
原有的依赖弃用、子图 durability 和测试 SQLite 连接回收警告仍存在，不属于本次启动修复。
Ruff 与 `git diff --check` 通过。本次没有更新正在运行的业务容器。
