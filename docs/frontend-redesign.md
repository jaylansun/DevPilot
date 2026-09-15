# 前端工作台改版

## 设计方向

保留 Vue 3、TypeScript、Tailwind CSS 4 与 Element Plus。把原有浅色卡片表单改成深色项目工作台，视觉重心放在项目内容与对话上，不增加虚假的功能入口或统计数字。

- 背景 `#0b1019`，内容表面 `#141c2a`，浮层 `#1c2738`。
- 主要文字 `#edf3fc`，辅助文字 `#a8b6ca`，操作色 `#8ccfff`。
- 使用系统中文字体与 Segoe UI 字体栈，不依赖外网字体加载。
- 登录与 AI 空态使用局部 3D 核心；正文、输入与任务保持清晰的二维布局。

## 改了什么

| 文件 / 模块 | 作用 |
| --- | --- |
| `tailwind.css`、`AppLayout.vue` | 公共设计变量、Element Plus 暗色适配、导航与移动端空间分配 |
| `LoginView.vue`、`ProjectsView.vue`、`ProjectDetailView.vue` | 登录、项目列表、紧凑项目导航与功能入口 |
| `KnowledgeChat.vue` | 用户消息、助手回答、固定可达输入框、推荐问题、重试与取消 |
| `SafeMarkdown.vue`、`safe_markdown.ts` | 回答的列表、标题、代码和链接排版；禁止原始 HTML、图片与危险链接 |
| `TaskPlanning.vue` | 左侧目标交流，右侧草案、验收标准、依赖和来源预览 |
| `AiPresence.vue`、`graphics/ai_presence.ts` | 延迟加载的 WebGL2 圆环与球芯、暂停控制和静态降级 |
| 看板、知识库及表单组件 | 保留现有业务功能，统一暗色与状态颜色、触控尺寸 |

## 能力边界

问答仍只发送当前 `question`，不自动把此前记录作为上下文；本页最多临时展示 20 轮，刷新或离开清空。回答是完整返回后展示，不是流式生成。

任务规划仍只发送当前 `goal`，输出临时草案；尚未增加多轮修改、保存、审批或加入看板接口。取消按钮停止前端等待，不承诺中止服务端已开始的计算。

本次不修改后端接口、数据库、Jenkins 凭据或 `.env`。技能安装在本机用户技能目录，不需要打进项目镜像。部署时提交前端改动和锁文件，再执行原有 Jenkins 流水线即可。

## 性能与安全

3D 无外网资产或模型下载；限制 30fps、最大边 600 像素与 DPR 1.5。离屏和后台停止动画，减少动态偏好保持静态，低配或 WebGL 不可用时显示 SVG。组件销毁时清理监听器、观察器和图形资源。

Markdown 解析器固定版本，保留来源编号；来源摘录继续以纯文本展示。仅允许明确的 HTTP/HTTPS 链接，新窗口使用 `noopener noreferrer`，不向外部链接发送来源信息。

## 技能来源

主视觉参考 [frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design)，交互与可访问性参考 [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)。该技能的设计搜索偏向宣传页，因此未直接采用其布局输出；工作台布局依据 DevPilot 功能与用户确认的方向设计。

3D 方法参考 [shader-dev](https://github.com/MiniMax-AI/skills/tree/main/skills/shader-dev)，相关 MIT 许可声明保留在图形源码中。

## 验证

在 `vue` 目录运行 `npm test`、`npm run build`、`npm run test:e2e:preview`。浏览器用例使用本地 Chrome 和拦截数据，不调用真实模型或修改业务数据库；设计截图输出到已忽略的 `vue/test-results/screenshots/`。

本轮验证：47 项单元测试、32 项浏览器测试和生产构建通过；检查了桌面与手机截图，并验证 3D 暂停、减少动态与 WebGL 不可用时的静态降级。

本轮 `npm audit --omit=dev` 未发现生产依赖漏洞。完整依赖审计有既存的 Vitest 3 测试工具链中风险提示，本轮未进行无关的大版本升级。
