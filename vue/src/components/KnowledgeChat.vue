<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { ArrowDown, ChatLineRound, Document, Refresh, Top } from "@element-plus/icons-vue";
import { askKnowledge, getKnowledgeInfo } from "@/api/rag_api";
import { ApiError, errorMessage } from "@/api/http_client";
import AiPresence from "@/components/AiPresence.vue";
import SafeMarkdown from "@/components/SafeMarkdown.vue";
import type { RagAnswerVO, RagInfoVO } from "@/types/api";

const props = defineProps<{ projectId: string }>();
const route = useRoute();
const info = ref<RagInfoVO | null>(null);
const loading = ref(true);
const loadError = ref("");
const question = ref("");
const formError = ref("");
const composing = ref(false);
const chatPanel = ref<HTMLElement | null>(null);
const panelHeight = ref(360);
const questionInput = ref<HTMLTextAreaElement | null>(null);
const messageViewport = ref<HTMLElement | null>(null);
const followingLatest = ref(true);
const showLatestButton = ref(false);
const pendingTurnId = ref<number | null>(null);
const sending = computed(() => pendingTurnId.value !== null);
const canAsk = computed(
  () => !loading.value && !loadError.value && !!info.value?.configured && !!info.value.ready_documents,
);
type Turn = {
  id: number;
  question: string;
  answer?: RagAnswerVO;
  error?: string;
};
const turns = ref<Turn[]>([]);
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

function updatePanelHeight() {
  const panel = chatPanel.value;
  if (!panel || !active) return;
  // 使用文档坐标，让页面滚动不会改变面板高度；短横屏保留可操作的最小空间。
  const documentTop = panel.getBoundingClientRect().top + window.scrollY;
  const bottomGutter = window.innerWidth < 680 ? 16 : 20;
  panelHeight.value = Math.max(360, Math.floor(window.innerHeight - documentTop - bottomGutter));
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
    const result = await getKnowledgeInfo(props.projectId);
    if (active && requestId === infoRequestId) info.value = result;
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

async function send(retryTurn?: Turn) {
  if (sending.value || !canAsk.value) return;
  const text = (retryTurn?.question ?? question.value).trim();
  if (!text || text.length > 2000) {
    formError.value = "请输入 1～2000 个字符的问题";
    questionInput.value?.focus();
    return;
  }
  formError.value = "";
  const turn: Turn = retryTurn ?? { id: nextId++, question: text };
  if (retryTurn) {
    turn.error = undefined;
    turn.answer = undefined;
    question.value = text;
  } else {
    turns.value.push(turn);
    // 只保留最近 20 轮页面记录，不持久存储问题或文档摘录。
    if (turns.value.length > 20) turns.value.shift();
  }
  const requestId = ++answerRequestId;
  const controller = new AbortController();
  requestController = controller;
  pendingTurnId.value = turn.id;
  void scrollToLatest();
  try {
    const answer = await askKnowledge(props.projectId, { question: text }, controller.signal);
    // 取消后即使底层请求仍然返回，也不能覆盖当前记录或后续提问。
    if (!active || controller.signal.aborted || requestId !== answerRequestId) return;
    const item = turns.value.find((value) => value.id === turn.id);
    if (item) item.answer = answer;
    if (question.value.trim() === text) question.value = "";
  } catch (reason) {
    if (!active || requestId !== answerRequestId) return;
    const item = turns.value.find((value) => value.id === turn.id);
    if (item)
      item.error = reason instanceof ApiError && reason.code === "cancelled"
        ? "已停止等待；服务端可能仍在结束当前计算。问题已保留，可再次发送。"
        : errorMessage(reason);
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

function clearHistory() {
  if (sending.value) return;
  turns.value = [];
  formError.value = "";
  followingLatest.value = true;
  showLatestButton.value = false;
  questionInput.value?.focus();
}

onMounted(() => {
  void loadInfo();
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
  active = false;
  ++answerRequestId;
  ++infoRequestId;
  requestController?.abort();
  window.removeEventListener("resize", schedulePanelHeight);
  if (heightFrame !== undefined) window.cancelAnimationFrame(heightFrame);
  layoutObserver?.disconnect();
});
</script>

<template>
  <section
    ref="chatPanel"
    aria-label="项目知识库问答"
    class="flex min-h-0 flex-col rounded-[28px] bg-surface pt-3 text-ink max-mobile:rounded-[20px] max-mobile:pt-1"
    :style="{ height: panelHeight + 'px' }"
  >
    <header class="mx-auto flex w-full max-w-[940px] shrink-0 items-center justify-between gap-3 px-6 py-1 max-mobile:px-2">
      <div class="flex min-w-0 items-center gap-2.5">
        <el-icon aria-hidden="true" class="text-brand" :size="18"><ChatLineRound /></el-icon>
        <h2 class="m-0 text-sm font-semibold">项目助手</h2>
        <span class="text-xs text-muted max-mobile:hidden">{{ loading ? "正在读取资料" : info?.ready_documents ? info.ready_documents + " 份资料就绪" : "项目知识库" }}</span>
      </div>
      <div class="flex shrink-0 items-center gap-1">
        <button
          v-if="turns.length"
          type="button"
          class="min-h-11 cursor-pointer rounded-xl px-3 text-xs text-muted transition-colors hover:bg-raised/70 hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="sending"
          @click="clearHistory"
        >清空记录</button>
        <button
          type="button"
          aria-label="刷新问答状态"
          title="刷新问答状态"
          class="flex size-11 cursor-pointer items-center justify-center rounded-xl text-muted transition-colors hover:bg-raised/70 hover:text-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-40"
          :disabled="sending || loading"
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
        <div class="mx-auto w-full max-w-[820px] px-6 pb-2 pt-1 max-mobile:px-2">
          <p v-if="loadError" class="ui-error m-0" role="alert">{{ loadError }}。请刷新问答状态后重试。</p>
          <template v-else-if="info">
            <p class="m-0 text-center text-xs leading-5 text-muted" role="status">
              <template v-if="info.mode === 'mock'">演示模式：展示检索摘录，不调用大模型。</template>
              <template v-else>真实模型模式：问题与相关片段将发送给模型服务，请核对回答引用。</template>
            </p>
            <p v-if="!info.configured" class="ui-error mb-0 mt-3" role="alert">
              真实问答尚未配置。请在服务器设置 MODEL_NAME、LLM_API_KEY 和 LLM_BASE_URL 后重新部署；不要在这里填写密钥。
            </p>
            <p v-else-if="!info.ready_documents" class="mb-0 mt-3 text-sm leading-7 text-muted">
              还没有已就绪的文档。请先到
              <RouterLink :to="{ path: route.path, query: { tab: 'documents' } }" class="rounded text-brand underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand">知识库上传资料</RouterLink>，索引完成后点击“刷新问答状态”。
            </p>
          </template>
        </div>

        <div v-if="!turns.length" class="mx-auto flex w-full max-w-[760px] flex-1 flex-col items-center justify-center px-6 pb-7 pt-2 text-center max-mobile:px-2 max-mobile:pb-4">
          <div class="size-[110px] shrink-0 max-mobile:size-[88px]"><AiPresence /></div>
          <h3 class="mb-0 mt-3 text-[32px] leading-[1.35] font-semibold tracking-[-0.03em] text-balance max-mobile:mt-2 max-mobile:text-[28px]">让资料回答你的问题</h3>
          <p class="mb-0 mt-2 text-[15px] leading-7 text-muted max-mobile:text-sm">梳理需求，核对规则，找到原文依据。</p>
          <div class="mt-6 flex flex-wrap justify-center gap-2.5 max-mobile:mt-4 max-mobile:gap-2" aria-label="推荐问题">
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
          aria-label="本页问答记录"
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
                  <span v-if="turn.answer" class="text-xs font-normal text-muted">{{ turn.answer.mode === "mock" ? "检索演示" : "AI 回答" }}<span class="ml-2">{{ turn.answer.status === "insufficient_evidence" ? "资料不足" : "附来源引用" }}</span></span>
                </p>
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
                  <div v-else key="waiting" class="py-1" role="status">
                    <p class="m-0 flex items-center gap-2.5 text-sm leading-7 text-muted"><span class="size-1.5 shrink-0 animate-pulse rounded-full bg-brand motion-reduce:animate-none" aria-hidden="true" />正在检索资料并准备回答，请稍候……</p>
                    <p class="mb-0 mt-1 text-xs leading-6 text-muted">完成后会显示回答和引用来源。</p>
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
        <div class="rounded-[22px] border border-line bg-surface px-4 pb-3 pt-3 shadow-lg shadow-ink/5 transition-[border-color,box-shadow] duration-200 focus-within:border-brand/60 focus-within:ring-2 focus-within:ring-brand/15 max-mobile:px-3">
          <label for="knowledge-question" class="mb-0.5 block text-xs font-medium text-muted">你想了解什么？</label>
          <textarea
            id="knowledge-question"
            ref="questionInput"
            v-model="question"
            rows="1"
            maxlength="2000"
            class="block min-h-12 w-full resize-none border-0 bg-transparent py-2 text-base leading-7 text-ink placeholder:text-muted/80 focus:outline-0 disabled:cursor-not-allowed disabled:opacity-40"
            placeholder="问问项目需求、业务规则或文档细节…"
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
        <p id="knowledge-history-help" class="mb-0 mt-2.5 text-center text-xs leading-5 text-muted">每轮独立检索，仅本页临时保留最近 20 轮；刷新或离开后清空。</p>
      </form>
    </div>
  </section>
</template>
