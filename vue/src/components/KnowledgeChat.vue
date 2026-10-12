<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElDrawer, ElPopconfirm } from "element-plus";
import { ArrowDown, ChatLineRound, Close, Document, Refresh, Top } from "@element-plus/icons-vue";
import { sendSessionChat, getChatInfo, listChatSessions, createChatSession, getChatSession, deleteChatSession } from "@/api/chat_api";
import { ApiError, errorMessage } from "@/api/http_client";
import RunTrace from "@/components/RunTrace.vue";
import type { TraceEvent } from "@/types/stream";
import AiPresence from "@/components/AiPresence.vue";
import SafeMarkdown from "@/components/SafeMarkdown.vue";
import ChatArtifactDetail from "@/components/ChatArtifactDetail.vue";
import PlanDraftList from "@/components/PlanDraftList.vue";
import PlanningApprovals from "@/components/PlanningApprovals.vue";
import ApprovalDetails from "@/components/ApprovalDetails.vue";
import { getDraft } from "@/api/plan_draft_api";
import { getApproval } from "@/api/approval_api";
import type { ApprovalVO, ChatAnswerVO, ChatArtifactVO, ChatInfoVO, ChatIntent, ChatSessionVO, PlanDraftVO, SavedChatMessageVO } from "@/types/api";

const props = defineProps<{ projectId: string }>();
const route = useRoute();
const router = useRouter();
const sessionId = ref<string | null>(null);
const sessions = ref<ChatSessionVO[]>([]);
const sessionsMore = ref(false);
const historyOpen = ref(false);
const recordsOpen = ref(false);
const recordsTab = ref<"drafts" | "approvals">("drafts");
const draftsRefresh = ref(0), approvalsRefresh = ref(0);
const submittedApproval = ref<ApprovalVO | null>(null);
const artifactBusy = ref(false), artifactEditing = ref(false), linkLoading = ref(false);
const detailsLocked = computed(() => artifactBusy.value || artifactEditing.value || linkLoading.value);
const draftStates = ref<Record<string, PlanDraftVO>>({});
type Detail = { key: string; artifact: ChatArtifactVO; initialDraft?: PlanDraftVO };
const detail = ref<Detail | null>(null);
const approvalDetail = ref<ApprovalVO | null>(null);
const detailOpen = computed(() => !!detail.value || !!approvalDetail.value);
const mobileDetails = ref(window.innerWidth < 1024);
const detailTitle = computed(() => approvalDetail.value ? "审批详情" : detail.value?.artifact.type === "task_plan" ? "任务草案" : "需求检查报告");
const intent = ref<ChatIntent>(route.query.tab === "planning" ? "task_planning" : route.query.tab === "assistant" ? "requirement_check" : "auto");
const intentOptions: { value: ChatIntent; label: string; placeholder: string }[] = [
  { value: "auto", label: "自动处理", placeholder: "问问项目，或说说下一步目标…" },
  { value: "task_planning", label: "生成任务草案", placeholder: "描述目标和范围，例如：完善下单流程，明确任务和验收标准。" },
  { value: "requirement_check", label: "检查需求缺口", placeholder: "描述检查范围，例如：对照需求文档，检查下单流程还有哪些遗漏。" },
];
const inputPlaceholder = computed(() => intentOptions.find(option => option.value === intent.value)!.placeholder);
const hasOlder = ref(false);
const sessionLoading = ref(false);
let sessionRequestId = 0;
let pendingPoll: ReturnType<typeof setTimeout> | undefined;
const info = ref<ChatInfoVO | null>(null);
const loading = ref(true);
const loadError = ref("");
const question = ref("");
const formError = ref("");
const composing = ref(false);
const chatPanel = ref<HTMLElement | null>(null);
const panelHeight = ref(360);
const compactPanel = computed(() => panelHeight.value < 560);
const questionInput = ref<HTMLTextAreaElement | null>(null);
const detailPanel = ref<HTMLElement | null>(null);
const messageViewport = ref<HTMLElement | null>(null);
const followingLatest = ref(true);
const showLatestButton = ref(false);
const pendingTurnId = ref<number | null>(null);
const sending = computed(() => pendingTurnId.value !== null);
const canAsk = computed(
  () => !loading.value && !sessionLoading.value && !detailsLocked.value && !turns.value.some(t => t.pending) && !loadError.value && !!info.value?.configured,
);
type Turn = {
  id: number;
  question: string;
  intent: ChatIntent;
  answer?: ChatAnswerVO;
  clientId: string;
  seq?: number;
  pending?: boolean;
  error?: string;
  draft?: string;
  trace: TraceEvent[];
};
const turns = ref<Turn[]>([]);
const taskLabels = { todo: "待办", in_progress: "进行中", done: "已完成" };
const suggestions = [
  { title: "梳理项目", question: "项目资料中描述了哪些核心功能？" },
  { title: "核对规则", question: "资料中有哪些必须遵守的业务规则和限制？" },
  { title: "发现缺口", question: "根据现有资料，哪些需求还需要进一步明确？" },
];
let nextId = 1;
let active = true;
let infoRequestId = 0;
let answerRequestId = 0;
let requestController: AbortController | undefined;
let heightFrame: number | undefined;
let layoutObserver: ResizeObserver | undefined;
let scrollingToLatest = false;
let linkController: AbortController | undefined;
let linkRequestId = 0;

function updatePanelHeight() {
  const panel = chatPanel.value;
  if (!panel || !active) return;
  // 使用文档坐标，让页面滚动不会改变面板高度；短横屏保留可操作的最小空间。
  const documentTop = panel.getBoundingClientRect().top + window.scrollY;
  const bottomGutter = 16;
  panelHeight.value = Math.max(360, Math.floor(window.innerHeight - documentTop - bottomGutter));
  mobileDetails.value = window.innerWidth < 1024;
}

function schedulePanelHeight() {
  if (heightFrame !== undefined || !active) return;
  heightFrame = window.requestAnimationFrame(() => {
    heightFrame = undefined;
    updatePanelHeight();
    resizeQuestionInput();
    void followLatestIfNeeded();
  });
}

async function loadInfo() {
  const requestId = ++infoRequestId;
  loading.value = true;
  loadError.value = "";
  try {
    const project = props.projectId;
    const [result, saved] = await Promise.all([getChatInfo(project), listChatSessions(project)]);
    if (!active || requestId !== infoRequestId) return;
    info.value = result;
    sessions.value = saved;
    sessionsMore.value = saved.length === 50;
    const selected = sessionId.value ?? (typeof route.query.chat_session === "string" ? route.query.chat_session : saved[0]?.id);
    if (selected) await selectSession(selected);
  } catch (reason) {
    if (active && requestId === infoRequestId) loadError.value = errorMessage(reason);
  } finally {
    if (active && requestId === infoRequestId) loading.value = false;
  }
}

function updateScrollPosition() {
  const viewport = messageViewport.value;
  if (!viewport) return;
  const distanceToBottom = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight;
  const isNearBottom = distanceToBottom < 64;
  if (scrollingToLatest && distanceToBottom > 1) return;
  if (distanceToBottom <= 1) scrollingToLatest = false;
  followingLatest.value = isNearBottom;
  showLatestButton.value = !!turns.value.length && !isNearBottom;
}

async function scrollToLatest(smooth = false) {
  await nextTick();
  const viewport = messageViewport.value;
  if (!viewport || !active) return;
  followingLatest.value = true;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  scrollingToLatest = smooth && !reducedMotion;
  viewport.scrollTo({ top: viewport.scrollHeight, behavior: scrollingToLatest ? "smooth" : "auto" });
  showLatestButton.value = false;
}

async function followLatestIfNeeded() {
  // 空态没有“最新消息”，不要把欢迎内容自动滚出可视区域。
  if (!turns.value.length) return;
  // 只有仍停留在最新消息处才跟随新内容，用户上翻阅读时保留位置。
  if (followingLatest.value) await scrollToLatest();
  else showLatestButton.value = !!turns.value.length;
}

async function jumpToLatest() {
  await scrollToLatest(true);
  questionInput.value?.focus({ preventScroll: true });
}

function stopAutomaticScroll() {
  if (!scrollingToLatest) return;
  scrollingToLatest = false;
  const viewport = messageViewport.value;
  if (!viewport) return;
  // 滚到当前像素位置会终止浏览器仍在执行的平滑滚动，让后续手势立即接管。
  viewport.scrollTo({ top: viewport.scrollTop, left: viewport.scrollLeft, behavior: "instant" });
  updateScrollPosition();
}

function resizeQuestionInput() {
  const input = questionInput.value;
  if (!input) return;
  // 先还原自然高度，删除文字时也能收起；超过 140px 后只滚动输入内容。
  input.style.height = "auto";
  const contentHeight = input.scrollHeight;
  input.style.height = `${Math.min(140, Math.max(48, contentHeight))}px`;
  input.style.overflowY = contentHeight > 140 ? "auto" : "hidden";
}

watch(question, () => {
  resizeQuestionInput();
  void followLatestIfNeeded();
}, { flush: "post" });

function useSuggestion(text: string) {
  if (!canAsk.value || sending.value) return;
  question.value = text;
  formError.value = "";
  questionInput.value?.focus();
}

function savedTurn(message: SavedChatMessageVO, previous?: Turn): Turn {
  return { id: previous?.id ?? nextId++, clientId: message.client_message_id, seq: message.seq,
    question: message.question, intent: message.intent ?? "auto", answer: message.answer ?? undefined, trace: [],
    pending: message.status === "pending", error: message.error ?? undefined };
}

async function selectSession(id: string, close = true) {
  // 后台恢复仍要轮询当前会话；打开或编辑草案不能让 pending 消息永久停住。
  if (detailsLocked.value && (close || id !== sessionId.value)) return;
  const version = ++sessionRequestId;
  const project = props.projectId;
  sessionLoading.value = true;
  clearTimeout(pendingPoll);
  try {
    const result = await getChatSession(project, id);
    if (!active || project !== props.projectId || version !== sessionRequestId) return;
    const sameSession = sessionId.value === id;
    const earlier = sameSession ? turns.value.filter(t => t.seq && t.seq < (result.messages[0]?.seq ?? 0)) : [];
    const previous = sameSession ? new Map(turns.value.map(turn => [turn.clientId, turn])) : new Map<string, Turn>();
    if (!sameSession) { question.value = ""; formError.value = ""; detail.value = null; approvalDetail.value = null; }
    sessionId.value = id;
    turns.value = [...earlier, ...result.messages.map(message => savedTurn(message, previous.get(message.client_message_id)))];
    if (!earlier.length) hasOlder.value = result.has_more;
    if (close) historyOpen.value = false;
    await router.replace({ query: { ...route.query, chat_session: id } });
    if (close || followingLatest.value) void scrollToLatest();
    if (result.messages.some(m => m.status === "pending"))
      pendingPoll = setTimeout(() => { if (active && sessionId.value === id && !sending.value) void selectSession(id, false); }, 3000);
  } catch (reason) {
    if (active && version === sessionRequestId) formError.value = errorMessage(reason);
  } finally { if (active && version === sessionRequestId) sessionLoading.value = false; }
}

async function olderMessages() {
  if (!sessionId.value || sessionLoading.value || !turns.value[0]?.seq) return;
  const id = sessionId.value;
  sessionLoading.value = true;
  const viewport = messageViewport.value;
  const oldHeight = viewport?.scrollHeight ?? 0;
  try {
    const result = await getChatSession(props.projectId, id, turns.value[0].seq);
    if (!active || id !== sessionId.value) return;
    turns.value.unshift(...result.messages.map(message => savedTurn(message)));
    hasOlder.value = result.has_more;
    await nextTick();
    if (viewport) viewport.scrollTop += viewport.scrollHeight - oldHeight;
  } catch (reason) { formError.value = errorMessage(reason); }
  finally { sessionLoading.value = false; }
}

async function loadSessions(more = false) {
  const project = props.projectId;
  try {
    const result = await listChatSessions(project, more ? sessions.value.length : 0);
    if (!active || project !== props.projectId) return;
    sessions.value = more ? [...sessions.value, ...result] : result;
    sessionsMore.value = result.length === 50;
  } catch (reason) { formError.value = errorMessage(reason); }
}

async function removeSession(id: string) {
  try {
    await deleteChatSession(props.projectId, id);
    if (sessionId.value === id) {
      ++sessionRequestId; clearTimeout(pendingPoll);
      sessionId.value = null; turns.value = []; hasOlder.value = false; detail.value = null; approvalDetail.value = null;
      await router.replace({ query: { ...route.query, chat_session: undefined } });
    }
    await loadSessions();
  } catch (reason) { formError.value = errorMessage(reason); }
}

function selectIntent(value: ChatIntent) {
  if (sending.value || detailsLocked.value) return;
  intent.value = value;
  formError.value = "";
  questionInput.value?.focus({ preventScroll: true });
}
function artifactSummary(artifact: ChatArtifactVO) {
  if (artifact.type === "task_plan") {
    const saved = artifact.draft_id ? draftStates.value[artifact.draft_id] : undefined;
    const count = saved?.plan.proposal.tasks.length ?? artifact.result.proposal.tasks.length;
    const version = saved?.version ?? artifact.draft_version;
    return `${count} 项建议任务${version ? ` · 第 ${version} 版` : ""} · ${saved?.status === "submitted" ? "已提交审批" : artifact.draft_id ? "已保存" : "待保存"}`;
  }
  const report = artifact.result.report;
  return report ? `已覆盖 ${report.covered.length} · 可能遗漏 ${report.missing.length} · 待确认 ${report.questions.length}` : "检查范围与依据已保存在本条消息";
}
function openArtifact(turn: Turn, artifact: ChatArtifactVO, index: number) {
  if (detailsLocked.value) return;
  approvalDetail.value = null;
  detail.value = { key: `${turn.clientId}-${index}`, artifact };
  if (mobileDetails.value) void nextTick(() => detailPanel.value?.scrollIntoView({ block: "start" }));
  void router.replace({ query: { ...route.query, draft: artifact.type === "task_plan" ? artifact.draft_id ?? undefined : undefined, approval: undefined } });
}
function openDraft(draft: PlanDraftVO) {
  if (sending.value || detailsLocked.value) return;
  approvalDetail.value = null;
  draftStates.value[draft.id] = draft;
  detail.value = { key: `draft-${draft.id}`, initialDraft: draft, artifact: { type: "task_plan", goal: draft.goal, result: draft.plan, draft_id: draft.id, draft_version: draft.version } };
  recordsOpen.value = false;
  if (mobileDetails.value) void nextTick(() => detailPanel.value?.scrollIntoView({ block: "start" }));
  void router.replace({ query: { ...route.query, draft: draft.id, approval: undefined } });
}
function updateDraft(draft: PlanDraftVO) { draftStates.value[draft.id] = draft; draftsRefresh.value++; }
function draftSubmitted(approval: ApprovalVO) { submittedApproval.value = approval; approvalsRefresh.value++; }
function closeDetail() {
  if (detailsLocked.value) return;
  detail.value = null; approvalDetail.value = null;
  if (mobileDetails.value) void nextTick(() => chatPanel.value?.scrollIntoView({ block: "start" }));
  void router.replace({ query: { ...route.query, draft: undefined, approval: undefined } });
}
function prepareGapPlan(goal: string) {
  if (sending.value || detailsLocked.value) return;
  intent.value = "task_planning";
  question.value = goal.slice(0, 2000);
  formError.value = "";
  if (mobileDetails.value) closeDetail();
  void nextTick(() => questionInput.value?.focus({ preventScroll: true }));
}
async function loadLinkedDetail() {
  const draftId = typeof route.query.draft === "string" ? route.query.draft : undefined;
  const approvalId = typeof route.query.approval === "string" ? route.query.approval : undefined;
  if ((!draftId && !approvalId) || detailsLocked.value || sending.value) return;
  if (draftId && detail.value?.artifact.type === "task_plan" && detail.value.artifact.draft_id === draftId) return;
  if (!draftId && approvalDetail.value?.id === approvalId) return;
  linkController?.abort();
  const current = new AbortController(); linkController = current;
  const version = ++linkRequestId;
  linkLoading.value = true;
  try {
    if (draftId) {
      const draft = await getDraft(props.projectId, draftId, current.signal);
      if (!active || current.signal.aborted || version !== linkRequestId) return;
      draftStates.value[draft.id] = draft; approvalDetail.value = null;
      detail.value = { key: `draft-${draft.id}`, initialDraft: draft, artifact: { type: "task_plan", goal: draft.goal, result: draft.plan, draft_id: draft.id, draft_version: draft.version } };
    } else if (approvalId) {
      const approval = await getApproval(approvalId, current.signal);
      if (!active || current.signal.aborted || version !== linkRequestId) return;
      if (approval.project_id !== props.projectId) throw new Error("这份审批记录不属于当前项目");
      approvalDetail.value = approval; detail.value = null;
    }
  } catch (reason) { if (active && !current.signal.aborted && version === linkRequestId) formError.value = errorMessage(reason); }
  finally { if (active && version === linkRequestId) linkLoading.value = false; }
}
watch(() => [route.query.draft, route.query.approval], () => { if (!loading.value) void loadLinkedDetail(); });
watch(() => route.query.chat_session, value => {
  if (typeof value === "string" && value !== sessionId.value && !loading.value && !sending.value && !detailsLocked.value) void selectSession(value);
});
watch(detailsLocked, value => {
  if (value || loading.value || sending.value) return;
  const id = route.query.chat_session;
  if (typeof id === "string" && id !== sessionId.value) void selectSession(id);
});

async function send(retryTurn?: Turn) {
  if (sending.value || !canAsk.value) return;
  const text = (retryTurn?.question ?? question.value).trim();
  if (!text || text.length > 2000) {
    formError.value = "请输入 1～2000 个字符的问题";
    questionInput.value?.focus();
    return;
  }
  formError.value = "";
  const turn: Turn = retryTurn ?? { id: nextId++, question: text, intent: intent.value, clientId: crypto.randomUUID(), trace: [] };
  if (retryTurn) {
    turn.error = undefined;
    turn.answer = undefined;
    turn.draft = "";
    turn.trace = [];
    question.value = text;
  } else {
    turns.value.push(turn);
  }
  const requestId = ++answerRequestId;
  const controller = new AbortController();
  requestController = controller;
  pendingTurnId.value = turn.id;
  void scrollToLatest();
  try {
    const project = props.projectId;
    if (!sessionId.value) {
      const created = await createChatSession(project);
      if (!active || controller.signal.aborted || requestId !== answerRequestId) return;
      sessionId.value = created.id;
      await router.replace({ query: { ...route.query, chat_session: created.id } });
    }
    const answer = await sendSessionChat(project, sessionId.value, { question: text, intent: turn.intent, client_message_id: turn.clientId }, controller.signal, (event) => {
      if (!active || controller.signal.aborted || requestId !== answerRequestId) return;
      const item = turns.value.find((value) => value.id === turn.id);
      if (!item) return;
      if (event.type === "token") item.draft = (item.draft ?? "") + event.text;
      else if (event.type === "node" || event.type === "tool") item.trace.push(event);
      void followLatestIfNeeded();
    });
    // 取消后即使底层请求仍然返回，也不能覆盖当前记录或后续提问。
    if (!active || controller.signal.aborted || requestId !== answerRequestId) return;
    const item = turns.value.find((value) => value.id === turn.id);
    if (item) {
      item.answer = answer; item.draft = "";
      const artifact = answer.artifacts?.[0];
      if (artifact && !detailsLocked.value) openArtifact(item, artifact, 0);
    }
    if (question.value.trim() === text) question.value = "";
    void loadSessions();
  } catch (reason) {
    if (!active || requestId !== answerRequestId) return;
    const item = turns.value.find((value) => value.id === turn.id);
    if (item) item.draft = "";
    if (item)
      item.error = reason instanceof ApiError && reason.code === "cancelled"
        ? "已停止等待；服务端可能仍在结束当前计算。问题已保留，可再次发送。"
        : errorMessage(reason) + (reason instanceof ApiError && reason.requestId ? `（请求编号：${reason.requestId}）` : "");
  } finally {
    if (active && requestId === answerRequestId) {
      pendingTurnId.value = null;
      requestController = undefined;
      void followLatestIfNeeded();
      await nextTick();
      if (followingLatest.value && document.activeElement === document.body)
        questionInput.value?.focus({ preventScroll: true });
    }
  }
}

function stopWaiting() {
  const item = turns.value.find((value) => value.id === pendingTurnId.value);
  if (!item) return;
  ++answerRequestId;
  requestController?.abort();
  requestController = undefined;
  pendingTurnId.value = null;
  item.draft = "";
  item.error = "已停止等待；服务端可能仍在结束当前计算。问题已保留，可再次发送。";
  void nextTick(() => questionInput.value?.focus({ preventScroll: true }));
}

function handleQuestionKeydown(event: KeyboardEvent) {
  if (
    event.key !== "Enter" || event.shiftKey || event.ctrlKey || event.altKey || event.metaKey ||
    event.isComposing || composing.value || event.keyCode === 229
  ) return;
  event.preventDefault();
  void send();
}

async function clearHistory() {
  if (sending.value || sessionLoading.value || detailsLocked.value) return;
  sessionLoading.value = true;
  formError.value = "";
  try {
    const project = props.projectId;
    const result = await createChatSession(project);
    if (!active || project !== props.projectId) return;
    await selectSession(result.id);
    closeDetail();
    question.value = "";
    await loadSessions();
    questionInput.value?.focus();
  } catch (reason) { formError.value = errorMessage(reason); }
  finally { sessionLoading.value = false; }
}

watch(() => props.projectId, () => {
  ++answerRequestId;
  ++sessionRequestId;
  clearTimeout(pendingPoll);
  sessionId.value = null;
  sessions.value = [];
  sessionLoading.value = false;
  hasOlder.value = false;
  historyOpen.value = false;
  recordsOpen.value = false;
  detail.value = null; approvalDetail.value = null;
  draftStates.value = {};
  artifactBusy.value = false; artifactEditing.value = false;
  linkController?.abort(); ++linkRequestId; linkLoading.value = false;
  requestController?.abort();
  pendingTurnId.value = null;
  turns.value = [];
  question.value = "";
  formError.value = "";
  info.value = null;
  followingLatest.value = true;
  showLatestButton.value = false;
  void loadInfo();
});

onMounted(() => {
  void loadInfo().then(loadLinkedDetail);
  updatePanelHeight();
  resizeQuestionInput();
  window.addEventListener("resize", schedulePanelHeight);
  if (typeof ResizeObserver !== "undefined") {
    layoutObserver = new ResizeObserver(schedulePanelHeight);
    // 项目标题、导航换行或外围工作区尺寸变化后，重新测量剩余空间。
    let element = chatPanel.value?.parentElement;
    while (element && element !== document.body) {
      layoutObserver.observe(element);
      for (const sibling of element.children) {
        if (sibling !== chatPanel.value) layoutObserver.observe(sibling);
      }
      element = element.parentElement;
    }
  }
});
onBeforeUnmount(() => {
  ++sessionRequestId;
  clearTimeout(pendingPoll);
  active = false;
  ++answerRequestId;
  ++infoRequestId;
  requestController?.abort();
  linkController?.abort(); ++linkRequestId;
  window.removeEventListener("resize", schedulePanelHeight);
  if (heightFrame !== undefined) window.cancelAnimationFrame(heightFrame);
  layoutObserver?.disconnect();
});
</script>

<template>
  <section
    ref="chatPanel"
    aria-label="项目聊天助手"
    class="grid min-h-0 min-w-0 overflow-hidden rounded-[20px] bg-surface text-ink"
    :class="detailOpen && !mobileDetails ? 'grid-cols-[minmax(0,1fr)_minmax(340px,460px)]' : 'grid-cols-1'"
    :style="{ height: (panelHeight + (detailOpen && mobileDetails ? Math.min(520, panelHeight) : 0)) + 'px', gridTemplateRows: detailOpen && mobileDetails ? `${panelHeight}px ${Math.min(520, panelHeight)}px` : 'minmax(0,1fr)' }"
  >
    <div class="flex min-h-0 min-w-0 flex-col overflow-hidden pt-2 max-mobile:pt-1">
    <header class="mx-auto flex w-full max-w-[940px] shrink-0 flex-wrap items-center justify-between gap-x-3 gap-y-0 px-6 py-1 max-mobile:px-2">
      <div class="flex min-w-0 items-center gap-2.5">
        <el-icon aria-hidden="true" class="text-brand" :size="18"><ChatLineRound /></el-icon>
        <h2 class="m-0 text-sm font-semibold">项目助手</h2>
        <span v-if="!detailOpen" class="text-xs text-muted max-mobile:hidden">{{ loading ? "正在读取状态" : info?.ready_documents ? info.ready_documents + " 份资料可查询" : "随时开始聊天" }}</span>
      </div>
      <div class="flex shrink-0 items-center gap-1">
        <button
          type="button"
          class="min-h-11 cursor-pointer rounded-xl px-3 text-xs text-muted transition-colors hover:bg-raised/70 hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="sending || sessionLoading || detailsLocked"
          @click="clearHistory"
        >新对话</button>
        <button type="button" class="min-h-11 cursor-pointer rounded-xl px-2 text-xs text-muted hover:bg-raised" :disabled="sending || sessionLoading || detailsLocked" @click="historyOpen = true; loadSessions()">历史</button>
        <button type="button" class="min-h-11 cursor-pointer rounded-xl px-2 text-xs text-muted hover:bg-raised disabled:opacity-40" :disabled="sending || detailsLocked" @click="recordsOpen = true">草案与审批</button>
        <button
          type="button"
          aria-label="刷新问答状态"
          title="刷新问答状态"
          class="flex size-11 cursor-pointer items-center justify-center rounded-xl text-muted transition-colors hover:bg-raised/70 hover:text-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="sending || loading || detailsLocked"
          @click="loadInfo"
        ><el-icon aria-hidden="true" :size="17" :class="{ 'animate-spin motion-reduce:animate-none': loading }"><Refresh /></el-icon></button>
      </div>
    </header>

    <div
      ref="messageViewport"
      class="min-h-0 flex-1 overflow-y-auto overscroll-contain scroll-pt-6 scroll-pb-20 [&_summary]:scroll-mb-16 [&_a]:scroll-mb-16 [&_button]:scroll-mb-16"
      data-testid="chat-scroll-region"
      @scroll.passive="updateScrollPosition"
      @wheel.passive="stopAutomaticScroll"
      @touchstart.passive="stopAutomaticScroll"
      @pointerdown="stopAutomaticScroll"
      @keydown="stopAutomaticScroll"
    >
      <div class="flex min-h-full flex-col">
        <button v-if="hasOlder" class="mx-auto my-3 min-h-11 text-sm text-brand" :disabled="sessionLoading" @click="olderMessages">加载更早消息</button>
        <p v-if="turns.some(t => t.pending)" role="status" class="text-center text-xs text-muted">服务端正在处理，完成后会自动更新。</p>
        <div class="mx-auto w-full max-w-[820px] px-6 pb-2 pt-1 max-mobile:px-2">
          <p v-if="loadError" class="ui-error m-0" role="alert">{{ loadError }}。请刷新问答状态后重试。</p>
          <template v-else-if="info">
            <p class="m-0 text-center text-xs leading-5 text-muted" role="status">
              <template v-if="info.mode === 'mock'">演示模式：固定问候与真实资料查询，不调用大模型。</template>
              <template v-else>可以自由聊天、查询资料与任务，也能生成草案和检查需求；项目回答请核对依据。</template>
            </p>
            <p v-if="!info.configured" class="ui-error mb-0 mt-3" role="alert">
              聊天模型尚未配置，请联系管理员完成配置后刷新。
            </p>
            <p v-else-if="!info.ready_documents" class="mb-0 mt-3 text-sm leading-7 text-muted">
              还没有已就绪的文档，可以直接聊天或查询任务。需要了解项目资料时，可到
              <RouterLink :to="{ path: route.path, query: { tab: 'documents' } }" class="rounded text-brand underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand">知识库上传资料</RouterLink>。
            </p>
          </template>
        </div>

        <div v-if="!turns.length" class="mx-auto flex w-full max-w-[760px] flex-1 flex-col items-center justify-center px-6 text-center max-mobile:px-2" :class="compactPanel ? 'pb-2 pt-1' : 'pb-4 pt-2'">
          <div class="flex items-center" :class="compactPanel ? 'gap-3 max-mobile:gap-2' : 'flex-col'">
            <div class="shrink-0" :class="compactPanel ? 'size-8' : 'size-[88px] max-mobile:size-[72px]'"><AiPresence /></div>
            <h3 class="mb-0 leading-[1.35] font-semibold tracking-[-0.03em] text-balance" :class="compactPanel ? 'mt-0 text-2xl max-mobile:text-xl' : 'mt-3 text-[28px] max-mobile:mt-2 max-mobile:text-2xl'">聊聊想法，也聊聊项目</h3>
          </div>
          <p class="mb-0 mt-2 text-[15px] text-muted max-mobile:text-sm" :class="compactPanel ? 'leading-6' : 'leading-7'">直接描述你的问题或目标，资料、草案和检查结果都在这里接着看。</p>
          <div class="flex flex-wrap justify-center gap-2.5 max-mobile:gap-2" :class="compactPanel ? 'mt-2' : 'mt-5 max-mobile:mt-4'" aria-label="推荐问题">
            <button
              v-for="suggestion in suggestions"
              :key="suggestion.title"
              type="button"
              class="min-h-11 cursor-pointer rounded-full border border-line bg-surface px-5 py-2.5 text-[13px] text-ink transition-[background-color,border-color,color] duration-200 hover:border-brand/30 hover:bg-brand/5 hover:text-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand active:bg-brand/10 disabled:cursor-not-allowed disabled:opacity-40 max-mobile:px-3.5"
              :aria-label="suggestion.title + '：' + suggestion.question"
              :disabled="!canAsk || sending"
              @click="useSuggestion(suggestion.question)"
            >{{ suggestion.title }}</button>
          </div>
        </div>

        <TransitionGroup
          v-else
          tag="div"
          appear
          class="mx-auto w-full max-w-[820px] space-y-10 px-6 pb-20 pt-5 max-mobile:px-2 max-mobile:pt-4"
          role="log"
          aria-live="polite"
          aria-relevant="additions text"
          aria-label="会话问答记录"
          enter-active-class="transition-[opacity,transform] duration-200 ease-out motion-reduce:transition-none"
          enter-from-class="translate-y-2 opacity-0 motion-reduce:translate-y-0"
          enter-to-class="translate-y-0 opacity-100"
          move-class="transition-transform duration-200 motion-reduce:transition-none"
          @after-enter="followLatestIfNeeded"
        >
          <article v-for="turn in turns" :key="turn.id" class="min-w-0" :aria-label="'问题：' + turn.question">
            <div class="mb-6 flex justify-end">
              <div class="max-w-[85%] rounded-[22px] rounded-tr-md bg-raised/80 px-5 py-3 max-mobile:max-w-[92%] max-mobile:px-4">
                <h3 class="m-0 text-base font-normal leading-[1.85] whitespace-pre-wrap wrap-anywhere"><span class="sr-only">你：</span>{{ turn.question }}</h3>
              </div>
            </div>
            <div class="flex min-w-0 gap-3 max-mobile:gap-2.5">
              <span class="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-brand/7 text-brand">
                <el-icon aria-hidden="true" :size="16"><ChatLineRound /></el-icon>
              </span>
              <div class="min-w-0 flex-1">
                <p class="mb-3 mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm font-semibold">
                  项目助手
                  <span v-if="turn.answer" class="text-xs font-normal text-muted">{{ turn.answer.mode === "mock" ? "演示回答" : "AI 回答" }}<span class="ml-2">{{ turn.answer.status === "insufficient_evidence" ? "资料不足" : turn.answer.basis === "general" ? "未查询项目资料" : turn.answer.artifacts?.length ? "结果已保存" : turn.answer.sources.length ? "附来源引用" : "任务查询" }}</span></span>
                </p>
                <RunTrace :events="turn.trace" :running="pendingTurnId === turn.id" />
                <Transition
                  mode="out-in"
                  enter-active-class="transition-opacity duration-200 ease-out motion-reduce:transition-none"
                  enter-from-class="opacity-0"
                  enter-to-class="opacity-100"
                  leave-active-class="transition-opacity duration-100 ease-in motion-reduce:transition-none"
                  leave-from-class="opacity-100"
                  leave-to-class="opacity-0"
                  @after-enter="followLatestIfNeeded"
                >
                  <div v-if="turn.error" key="error">
                    <p class="ui-error m-0" role="alert">{{ turn.error }}</p>
                    <button type="button" class="mt-3 inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-full border border-line px-4 text-sm text-ink transition-colors hover:border-brand/30 hover:bg-brand/5 hover:text-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-40" :disabled="sending || !canAsk" @click="send(turn)">
                      <el-icon aria-hidden="true"><Refresh /></el-icon>重试此问题
                    </button>
                  </div>
                  <div v-else-if="turn.answer" key="answer">
                    <SafeMarkdown :content="turn.answer.answer" />
                    <div v-if="turn.answer.artifacts?.length" class="mt-4 space-y-3" aria-label="本次生成结果">
                      <button v-for="(artifact, index) in turn.answer.artifacts" :key="`${turn.clientId}-${index}`" type="button" class="block w-full cursor-pointer rounded-xl border border-brand/20 bg-brand/3 p-4 text-left transition-colors hover:border-brand/50 focus-visible:outline-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-50" :disabled="detailsLocked" :aria-label="artifact.type === 'task_plan' ? '打开任务草案' : '打开需求检查报告'" :aria-pressed="detail?.key === `${turn.clientId}-${index}`" @click="openArtifact(turn, artifact, index)">
                        <span class="block text-sm font-semibold">{{ artifact.type === 'task_plan' ? '任务草案' : '需求检查报告' }}</span>
                        <span class="mt-1 block text-xs leading-6 text-muted">{{ artifactSummary(artifact) }}</span>
                        <span class="mt-2 block text-xs text-brand">展开详情 →</span>
                      </button>
                    </div>
                    <details v-if="turn.answer.tasks.length" class="mt-5 rounded-xl border border-line/80 px-4 py-3" aria-label="查询到的任务">
                      <summary class="cursor-pointer text-sm text-muted">{{ turn.answer.tasks.length }} 项相关任务，可展开核对</summary>
                      <ul class="mb-0 mt-3 space-y-3 pl-4">
                        <li v-for="task in turn.answer.tasks" :key="task.id" class="text-sm leading-6 wrap-anywhere">
                          <span class="font-medium">{{ task.title }}</span>
                          <span class="ml-2 text-xs text-muted">{{ taskLabels[task.status] }}</span>
                          <p v-if="task.description" class="m-0 whitespace-pre-wrap text-muted">{{ task.description }}{{ task.description_truncated ? '…' : '' }}</p>
                        </li>
                      </ul>
                    </details>
                    <div v-if="turn.answer.sources.length" class="mt-6 space-y-2" aria-label="回答来源">
                      <p class="mb-2 text-xs text-muted">{{ turn.answer.sources.length }} 条来源，可展开核对</p>
                      <details v-for="source in turn.answer.sources" :key="source.source_id" class="group rounded-xl border border-line/80 transition-colors duration-150 open:bg-canvas/70">
                        <summary class="flex min-h-11 cursor-pointer list-none items-start justify-between gap-3 rounded-xl px-3 py-2.5 text-sm leading-6 text-ink transition-colors hover:bg-raised/50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand [&::-webkit-details-marker]:hidden">
                          <span class="flex min-w-0 items-start gap-2">
                            <el-icon aria-hidden="true" class="mt-1 shrink-0 text-muted"><Document /></el-icon>
                            <span class="wrap-anywhere"><span class="mr-1.5 text-brand">[{{ source.source_id }}]</span>{{ source.filename }}<span class="ml-2 text-xs text-muted">第 {{ source.chunk_index + 1 }} 个片段</span></span>
                          </span>
                          <el-icon aria-hidden="true" class="mt-1 shrink-0 text-muted transition-transform duration-150 group-open:rotate-180 motion-reduce:transition-none"><ArrowDown /></el-icon>
                        </summary>
                        <div class="px-4 pb-4 pt-1">
                          <p v-if="source.heading" class="mb-2 mt-0 text-xs leading-6 text-muted wrap-anywhere">{{ source.heading }}</p>
                          <blockquote class="m-0 border-l-2 border-brand/25 pl-3 text-sm leading-[1.85] text-muted whitespace-pre-wrap wrap-anywhere">{{ source.text }}</blockquote>
                        </div>
                      </details>
                    </div>
                  </div>
                  <div v-else-if="turn.draft" key="streaming" data-testid="streaming-answer">
                    <p class="mb-2 mt-0 text-xs text-muted">正在生成，回答与引用尚未校验</p>
                    <p class="m-0 text-base leading-[1.85] whitespace-pre-wrap wrap-anywhere">{{ turn.draft }}</p>
                  </div>
                  <div v-else key="waiting" class="py-1" role="status">
                    <p class="m-0 flex items-center gap-2.5 text-sm leading-7 text-muted"><span class="size-1.5 shrink-0 animate-pulse rounded-full bg-brand motion-reduce:animate-none" aria-hidden="true" />正在准备回答，需要时会查询项目资料或任务……</p>
                    <p class="mb-0 mt-1 text-xs leading-6 text-muted">回答将逐步显示，完成校验后展示引用来源。</p>
                  </div>
                </Transition>
              </div>
            </div>
          </article>
        </TransitionGroup>
      </div>
    </div>

    <div class="relative shrink-0 px-6 pb-3 pt-3 max-mobile:px-2">
      <Transition enter-active-class="transition-opacity duration-150 motion-reduce:transition-none" enter-from-class="opacity-0" leave-active-class="transition-opacity duration-100 motion-reduce:transition-none" leave-to-class="opacity-0">
        <div v-if="showLatestButton" class="pointer-events-none absolute inset-x-0 bottom-full flex justify-center pb-3">
          <button type="button" class="pointer-events-auto inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-full border border-line bg-surface px-4 text-xs font-medium text-ink shadow-sm transition-colors hover:border-brand/30 hover:text-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand" @click="jumpToLatest">
            <el-icon aria-hidden="true"><ArrowDown /></el-icon>回到最新
          </button>
        </div>
      </Transition>
      <form class="mx-auto max-w-[800px]" @submit.prevent="send()">
        <div class="mb-2 flex flex-wrap gap-1.5" aria-label="本次操作">
          <button v-for="option in intentOptions" :key="option.value" type="button" class="min-h-9 cursor-pointer rounded-full border px-3 text-xs transition-colors aria-pressed:border-brand/40 aria-pressed:bg-brand/8 aria-pressed:text-brand disabled:cursor-not-allowed disabled:opacity-40" :class="intent === option.value ? 'border-brand/40' : 'border-line text-muted hover:text-brand'" :aria-pressed="intent === option.value" :disabled="sending || detailsLocked" @click="selectIntent(option.value)">{{ option.label }}</button>
        </div>
        <div class="rounded-[22px] border border-line bg-surface px-4 pb-3 pt-3 shadow-lg shadow-ink/5 transition-[border-color,box-shadow] duration-200 focus-within:border-brand/60 focus-within:ring-2 focus-within:ring-brand/15 max-mobile:px-3">
          <label for="knowledge-question" class="mb-0.5 block text-xs font-medium text-muted">你想了解什么？</label>
          <textarea
            id="knowledge-question"
            ref="questionInput"
            v-model="question"
            rows="1"
            maxlength="2000"
            class="block min-h-12 w-full resize-none border-0 bg-transparent py-2 text-base leading-7 text-ink placeholder:text-muted/80 focus:outline-0 disabled:cursor-not-allowed disabled:opacity-40"
            :placeholder="inputPlaceholder"
            aria-describedby="knowledge-input-help knowledge-history-help"
            :aria-invalid="!!formError"
            :aria-errormessage="formError ? 'knowledge-form-error' : undefined"
            :disabled="sending || !canAsk"
            @compositionstart="composing = true"
            @compositionend="composing = false"
            @keydown="handleQuestionKeydown"
          />
          <p v-if="formError" id="knowledge-form-error" class="ui-error mb-2 mt-0" role="alert">{{ formError }}</p>
          <div class="mt-1 flex flex-wrap items-center justify-between gap-2">
            <span id="knowledge-input-help" class="text-xs leading-5 text-muted"><span class="tabular-nums">{{ question.length }} / 2000</span><span class="ml-3 max-mobile:hidden">Enter 发送，Shift + Enter 换行</span></span>
            <button v-if="sending" type="button" class="min-h-11 cursor-pointer rounded-full border border-line bg-raised/60 px-4 text-sm font-medium text-ink transition-colors hover:border-brand/30 hover:bg-raised focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand" @click="stopWaiting">停止等待</button>
            <button v-else type="submit" class="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-full bg-brand px-5 text-sm font-semibold text-white transition-[background-color,box-shadow] duration-150 hover:bg-brand/90 hover:shadow-md hover:shadow-brand/15 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand active:bg-brand/80 disabled:cursor-not-allowed disabled:opacity-40" :disabled="!canAsk || !question.trim()">
              发送问题<el-icon aria-hidden="true" :size="16"><Top /></el-icon>
            </button>
          </div>
        </div>
        <p id="knowledge-history-help" class="mb-0 mt-2.5 text-center text-xs leading-5 text-muted">{{ intent === 'task_planning' ? '草案自动保存，核对或编辑后提交审批，批准后才加入看板。' : intent === 'requirement_check' ? '报告随消息保存，检查范围与结论可以展开核对。' : '会话与生成结果自动保存，可以在历史中继续。' }}</p>
      </form>
    </div>
    </div>
    <aside v-if="detailOpen" ref="detailPanel" aria-label="结果详情" class="flex min-h-0 min-w-0 flex-col overflow-hidden bg-canvas/50" :class="mobileDetails ? 'border-t border-line' : 'border-l border-line'">
      <header class="flex shrink-0 items-center justify-between gap-3 border-b border-line px-4 py-2">
        <h2 class="m-0 text-sm font-semibold">{{ detailTitle }}</h2>
        <button type="button" aria-label="关闭结果详情" class="flex size-11 cursor-pointer items-center justify-center rounded-xl text-muted hover:bg-raised focus-visible:outline-brand disabled:opacity-40" :disabled="detailsLocked" @click="closeDetail"><el-icon :size="18"><Close /></el-icon></button>
      </header>
      <div class="min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-contain p-4">
        <ChatArtifactDetail v-if="detail" :key="detail.key" :project-id="projectId" :artifact="detail.artifact" :initial-draft="detail.initialDraft" :source-prefix="`chat-artifact-${detail.key}`" :disabled="sending" @update="updateDraft" @submitted="draftSubmitted" @busy="artifactBusy = $event" @editing="artifactEditing = $event" @plan="prepareGapPlan" />
        <ApprovalDetails v-else-if="approvalDetail" :approval="approvalDetail" />
      </div>
    </aside>
    <el-dialog v-model="historyOpen" title="会话历史" width="min(620px, 94vw)" class="ui-dialog" destroy-on-close>
      <p v-if="formError" role="alert" class="ui-error">{{ formError }}</p>
      <p class="text-sm text-muted">会话保存在账号下。删除后将清除这段对话的记录和上下文。</p>
      <p v-if="!sessions.length" class="text-muted">暂无已保存会话</p>
      <div v-for="item in sessions" :key="item.id" class="mb-2 flex items-center gap-2 rounded-xl border border-line p-3">
        <button class="min-w-0 flex-1 cursor-pointer text-left text-ink" :disabled="sessionLoading" @click="selectSession(item.id)">
          <span class="block truncate font-medium">{{ item.title }}</span>
          <span class="text-xs text-muted">{{ new Date(item.updated_at).toLocaleString() }}{{ item.id === sessionId ? ' · 当前会话' : '' }}</span>
        </button>
        <el-popconfirm title="删除此会话及其全部记录？" confirm-button-text="删除" cancel-button-text="取消" @confirm="removeSession(item.id)">
          <template #reference><el-button type="danger" text :disabled="sessionLoading">删除会话</el-button></template>
        </el-popconfirm>
      </div>
      <el-button v-if="sessionsMore" @click="loadSessions(true)">更多会话</el-button>
    </el-dialog>
    <el-drawer v-if="recordsOpen" v-model="recordsOpen" title="草案与审批记录" size="min(620px, 100vw)" append-to-body destroy-on-close>
      <div class="work-view-switch mb-4" aria-label="保存的结果">
        <button type="button" :aria-pressed="recordsTab === 'drafts'" @click="recordsTab = 'drafts'">已保存草案</button>
        <button type="button" :aria-pressed="recordsTab === 'approvals'" @click="recordsTab = 'approvals'">审批记录</button>
      </div>
      <PlanDraftList v-if="recordsTab === 'drafts'" :project-id="projectId" :refresh-key="draftsRefresh" :selected-id="detail?.artifact.type === 'task_plan' ? detail.artifact.draft_id ?? undefined : undefined" :disabled="sending || detailsLocked" @select="openDraft" />
      <PlanningApprovals v-else :project-id="projectId" :refresh-key="approvalsRefresh" :selected-approval="submittedApproval" :disabled="sending || detailsLocked" />
    </el-drawer>

  </section>
</template>
