<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ChatLineRound, Document, Refresh, Top } from "@element-plus/icons-vue";
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

async function scrollToLatest() {
  await nextTick();
  const viewport = messageViewport.value;
  if (viewport) viewport.scrollTop = viewport.scrollHeight;
}

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
      void scrollToLatest();
      await nextTick();
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
  questionInput.value?.focus();
}

onMounted(() => {
  void loadInfo();
  updatePanelHeight();
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
    class="flex min-h-0 flex-col overflow-hidden rounded-2xl border border-line bg-surface text-ink"
    :style="{ height: `${panelHeight}px` }"
  >
    <header class="flex shrink-0 items-center justify-between gap-3 border-b border-line px-5 py-3 max-mobile:px-4">
      <div class="flex min-w-0 items-center gap-3">
        <span class="flex size-9 shrink-0 items-center justify-center rounded-xl bg-brand/10 text-brand">
          <el-icon aria-hidden="true" :size="19"><ChatLineRound /></el-icon>
        </span>
        <div class="min-w-0">
          <h2 class="m-0 text-base font-semibold">项目助手</h2>
          <p class="m-0 mt-1 text-xs text-muted">
            {{ loading ? "正在读取资料状态" : info?.ready_documents ? `${info.ready_documents} 份就绪文档可供检索` : "基于项目知识库回答" }}
          </p>
        </div>
      </div>
      <div class="flex shrink-0 items-center gap-2">
        <button
          v-if="turns.length"
          type="button"
          class="min-h-11 cursor-pointer rounded-lg px-3 text-xs text-muted transition-colors hover:bg-raised hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="sending"
          @click="clearHistory"
        >清空记录</button>
        <button
          type="button"
          aria-label="刷新问答状态"
          title="刷新问答状态"
          class="flex size-11 cursor-pointer items-center justify-center rounded-lg text-muted transition-colors hover:bg-raised hover:text-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="sending || loading"
          @click="loadInfo"
        >
          <el-icon aria-hidden="true" :size="18" :class="{ 'animate-spin motion-reduce:animate-none': loading }"><Refresh /></el-icon>
        </button>
      </div>
    </header>

    <div ref="messageViewport" class="min-h-0 flex-1 overflow-y-auto overscroll-contain" data-testid="chat-scroll-region">
      <div class="mx-auto max-w-[860px] px-6 pt-4 max-mobile:px-4">
        <p v-if="loadError" class="ui-error m-0" role="alert">{{ loadError }}。请刷新问答状态后重试。</p>
        <template v-else-if="info">
          <p class="m-0 text-xs leading-6 text-muted" role="status">
            <template v-if="info.mode === 'mock'">演示模式：只展示检索摘录，不调用大模型，不生成推理回答。</template>
            <template v-else>真实模型模式：问题与相关片段会发送给已配置的模型服务。请核对回答引用。</template>
          </p>
          <p v-if="!info.configured" class="ui-error mt-3" role="alert">
            真实问答尚未配置。请在服务器设置 MODEL_NAME、LLM_API_KEY 和 LLM_BASE_URL 后重新部署；不要在这里填写密钥。
          </p>
          <p v-else-if="!info.ready_documents" class="mt-3 text-sm leading-7 text-muted">
            还没有已就绪的文档。请先到
            <RouterLink :to="{ path: route.path, query: { tab: 'documents' } }" class="rounded text-brand underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand">知识库上传资料</RouterLink>，索引完成后点击“刷新问答状态”。
          </p>
        </template>
      </div>

      <div v-if="!turns.length" class="mx-auto flex max-w-[760px] flex-col items-center px-6 pb-4 pt-3 text-center max-mobile:px-4 max-mobile:pt-0">
        <div class="flex items-center justify-center gap-5 text-left max-mobile:w-full max-mobile:gap-3">
          <div class="size-28 shrink-0 max-mobile:size-24"><AiPresence /></div>
          <div>
            <h3 class="m-0 text-2xl font-semibold tracking-tight max-mobile:text-xl max-mobile:leading-8">把项目资料，变成清晰答案</h3>
            <p class="mb-0 mt-2 max-w-[400px] text-sm leading-7 text-muted max-mobile:hidden">从一个具体问题开始。查找相关原文，理解业务规则，也能展开来源核对。</p>
          </div>
        </div>
        <div class="mt-4 grid w-full grid-cols-3 gap-3 max-mobile:mt-2 max-mobile:gap-2" aria-label="推荐问题">
          <button
            v-for="suggestion in suggestions"
            :key="suggestion.title"
            type="button"
            class="group min-h-20 cursor-pointer rounded-xl border border-line bg-canvas/40 p-3 text-left transition-colors hover:border-brand/60 hover:bg-raised focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-50 max-mobile:min-h-11 max-mobile:px-2 max-mobile:py-2.5 max-mobile:text-center"
            :aria-label="suggestion.title + '：' + suggestion.question"
            :disabled="!canAsk || sending"
            @click="useSuggestion(suggestion.question)"
          >
            <span class="mb-2 block text-sm font-medium text-ink max-mobile:mb-0">{{ suggestion.title }}</span>
            <span class="block text-xs leading-6 text-muted max-mobile:hidden">{{ suggestion.question }}</span>
          </button>
        </div>
      </div>

      <div v-else class="mx-auto max-w-[860px] space-y-9 px-6 py-7 max-mobile:px-4" role="log" aria-live="polite" aria-relevant="additions text" aria-label="本页问答记录">
        <article v-for="turn in turns" :key="turn.id" class="min-w-0" :aria-label="'问题：' + turn.question">
          <div class="mb-6 flex justify-end">
            <div class="max-w-[85%] rounded-2xl rounded-tr-md border border-line bg-raised px-5 py-3 max-mobile:max-w-[92%] max-mobile:px-4">
              <h3 class="m-0 text-base font-normal leading-7 whitespace-pre-wrap wrap-anywhere"><span class="sr-only">你：</span>{{ turn.question }}</h3>
            </div>
          </div>
          <div class="flex min-w-0 gap-3 max-mobile:gap-2.5">
            <span class="mt-1 flex size-8 shrink-0 items-center justify-center rounded-lg bg-brand/10 text-brand">
              <el-icon aria-hidden="true" :size="17"><ChatLineRound /></el-icon>
            </span>
            <div class="min-w-0 flex-1">
              <p class="mb-3 mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm font-medium">
                项目助手
                <span v-if="turn.answer" class="text-xs font-normal text-muted">{{ turn.answer.mode === "mock" ? "检索演示" : "AI 回答" }}<span class="ml-2">{{ turn.answer.status === "insufficient_evidence" ? "资料不足" : "附来源引用" }}</span></span>
              </p>
              <template v-if="turn.error">
                <p class="ui-error m-0" role="alert">{{ turn.error }}</p>
                <button type="button" class="mt-3 inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-lg border border-line px-3 text-sm text-ink transition-colors hover:bg-raised focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-50" :disabled="sending || !canAsk" @click="send(turn)">
                  <el-icon aria-hidden="true"><Refresh /></el-icon>重试此问题
                </button>
              </template>
              <template v-else-if="turn.answer">
                <SafeMarkdown :content="turn.answer.answer" />
                <div v-if="turn.answer.sources.length" class="mt-5 space-y-2" aria-label="回答来源">
                  <p class="mb-2 flex items-center gap-2 text-xs text-muted"><el-icon aria-hidden="true"><Document /></el-icon>{{ turn.answer.sources.length }} 条来源，可展开核对</p>
                  <details v-for="source in turn.answer.sources" :key="source.source_id" class="overflow-hidden rounded-xl border border-line bg-canvas/40">
                    <summary class="min-h-11 cursor-pointer px-4 py-3 text-sm leading-6 text-brand wrap-anywhere transition-colors hover:bg-raised focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand">[{{ source.source_id }}] {{ source.filename }}<span class="ml-2 text-xs text-muted">第 {{ source.chunk_index + 1 }} 个片段</span></summary>
                    <div class="border-t border-line px-4 py-3">
                      <p v-if="source.heading" class="mb-2 mt-0 text-xs leading-6 text-muted wrap-anywhere">{{ source.heading }}</p>
                      <blockquote class="m-0 border-l-2 border-brand/40 pl-3 text-sm leading-7 text-muted whitespace-pre-wrap wrap-anywhere">{{ source.text }}</blockquote>
                    </div>
                  </details>
                </div>
              </template>
              <div v-else class="py-1" role="status">
                <p class="m-0 flex items-center gap-2 text-sm leading-7 text-muted"><span class="size-2 shrink-0 animate-pulse rounded-full bg-brand motion-reduce:animate-none" aria-hidden="true" />正在检索资料并准备回答，请稍候……</p>
                <p class="mb-0 mt-2 text-xs leading-6 text-muted">完整回答会在处理结束后显示。</p>
              </div>
            </div>
          </div>
        </article>
      </div>
    </div>

    <div class="shrink-0 border-t border-line bg-surface px-6 pb-4 pt-4 max-mobile:px-3 max-mobile:pb-3">
      <form class="mx-auto max-w-[812px]" @submit.prevent="send()">
        <div class="rounded-2xl border border-line bg-canvas p-3 transition-colors focus-within:border-brand focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-brand">
          <label for="knowledge-question" class="mb-1 block text-xs font-medium text-muted">你想了解什么？</label>
          <textarea
            id="knowledge-question"
            ref="questionInput"
            v-model="question"
            rows="2"
            maxlength="2000"
            class="block max-h-40 min-h-[60px] w-full resize-none border-0 bg-transparent py-1 text-base leading-7 text-ink placeholder:text-muted focus:outline-0 disabled:cursor-not-allowed disabled:opacity-50"
            placeholder="询问项目需求、业务规则或文档细节…"
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
            <button v-if="sending" type="button" class="min-h-11 cursor-pointer rounded-xl border border-line bg-raised px-4 text-sm font-medium text-ink transition-colors hover:border-brand focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand" @click="stopWaiting">停止等待</button>
            <button v-else type="submit" class="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-xl bg-brand px-4 text-sm font-semibold text-canvas transition-colors hover:bg-brand/85 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:cursor-not-allowed disabled:opacity-40" :disabled="!canAsk || !question.trim()">
              发送问题<el-icon aria-hidden="true" :size="17"><Top /></el-icon>
            </button>
          </div>
        </div>
        <p id="knowledge-history-help" class="mb-0 mt-2 text-center text-xs leading-5 text-muted">每轮独立检索，仅本页临时保留最近 20 轮；刷新或离开后清空。</p>
      </form>
    </div>
  </section>
</template>
