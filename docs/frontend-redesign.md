# 前端工作台改版

## 设计方向

保留 Vue 3、TypeScript、Tailwind CSS 4 与 Element Plus。根据对第一版“太黑、密集、生硬”的反馈，本版改为浅色项目工作台：减少层层边框，用留白、字号和少量柔和阴影组织阅读。保留真实功能，不增加虚假的入口或统计数字。

- 背景 `#f7f8fa`，内容表面 `#ffffff`，次级表面 `#eef2f8`。
- 主要文字 `#202936`，辅助文字 `#637086`，操作色 `#365eea`。
- 使用系统中文字体与 Segoe UI 字体栈，不依赖外网字体加载；实际 Chrome 验证中文使用微软雅黑。回答正文为 16px、1.85 倍行高，主标题为 28～34px。
- 登录与问答空态使用小型玻璃“知识棱镜”，规划页面不再放置装饰动画。

## 改了什么

| 文件 / 模块 | 作用 |
| --- | --- |
| `tailwind.css`、`AppLayout.vue` | 浅色设计变量、Element Plus 适配、可收起侧栏、页面过渡与移动端空间分配 |
| `BrandMark.vue`、`ProjectTabs.vue` | 统一产品标记、带滑动选中块的项目标签导航 |
| `LoginView.vue`、`ProjectsView.vue`、`ProjectDetailView.vue` | 简洁登录、项目网格/列表切换、紧凑项目导航与功能入口 |
| `KnowledgeChat.vue` | 自适应输入框、保留历史阅读位置、回到最新、消息过渡、推荐问题、重试与取消 |
| `SafeMarkdown.vue`、`safe_markdown.ts` | 回答的列表、标题、代码和链接排版；禁止原始 HTML、图片与危险链接 |
| `TaskPlanning.vue` | 左侧目标交流与建议目标，右侧纸张式草案，按需展开验收、依赖、假设和来源 |
| `AiPresence.vue`、`graphics/ai_presence.ts` | 延迟加载的 WebGL2 玻璃棱镜、暂停控制和静态降级 |
| 看板、知识库及表单组件 | 浅灰看板与白色任务卡、简化文档上传列表、可展开的完整模型说明 |

## 能力边界

问答仍只发送当前 `question`，不自动把此前记录作为上下文；本页最多临时展示 20 轮，刷新或离开清空。回答是完整返回后展示，不是流式生成。

任务规划仍只发送当前 `goal`，输出临时草案；尚未增加多轮修改、保存、审批或加入看板接口。取消按钮停止前端等待，不承诺中止服务端已开始的计算。

本次不修改后端接口、数据库、Jenkins 凭据或 `.env`。技能安装在本机用户技能目录，不需要打进项目镜像。部署时提交本次前端改动，再执行原有 Jenkins 流水线即可；本次没有依赖或锁文件变更。

## 性能与安全

3D 无外网资产或模型下载；限制 30fps、最大边 600 像素与 DPR 1.5。离屏和后台停止动画，减少动态偏好保持静态，低配或 WebGL 不可用时显示 SVG。组件销毁时清理监听器、观察器和图形资源。

玻璃效果使用低成本透射近似，不是完整光路追踪。界面过渡使用 Vue 内置能力和 Tailwind，不新增依赖；以 100～280ms 的反馈和过渡为主，只动画透明度、变换或颜色，不靠延时模拟模型逐字输出。所有动画尊重减少动态偏好，业务状态不等待动画结束。

输入框随文字从 48px 增高到最多 140px，之后内部滚动；用户主动上翻后保留位置。回到最新按钮悬浮显示，不改变正文高度，滚动可被手动操作打断。

Markdown 解析器固定版本，保留来源编号；来源摘录继续以纯文本展示。仅允许明确的 HTTP/HTTPS 链接，新窗口使用 `noopener noreferrer`，不向外部链接发送来源信息。

## 技能来源

主视觉参考 [frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design)，交互与可访问性参考 [UI UX Pro Max](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)。该技能的设计搜索偏向宣传页，因此未直接采用其布局输出；工作台布局依据 DevPilot 功能与用户反馈设计。Vue 动画检索没有匹配项，具体实现采用 Vue 原生过渡与项目现有技术栈，而不是套用搜索结果。

3D 方法参考 [shader-dev](https://github.com/MiniMax-AI/skills/tree/main/skills/shader-dev)，相关 MIT 许可声明保留在图形源码中。

## 验证

在 `vue` 目录运行 `npm test`、`npm run build`、`npm run test:e2e:preview`。浏览器用例使用本地 Chrome 和拦截数据，不调用真实模型或修改业务数据库；设计截图输出到已忽略的 `vue/test-results/screenshots/`。

浅色改版验证：47 项单元测试、36 项浏览器测试和生产构建通过；覆盖 375px 手机、700/768px 窄窗口、812×375 横屏与 1440px 桌面，以及标签快速切换、侧栏焦点交接、输入自适高、历史滚动、键盘展开、减少动态和 WebGL 降级。截图关闭 CSS 过渡以截取稳定终态，动效行为另有浏览器断言。

上一版 `npm audit --omit=dev` 未发现生产依赖漏洞，本版没有修改依赖或锁文件。完整依赖审计有既存的 Vitest 3 测试工具链中风险提示，本轮未进行无关的大版本升级。
