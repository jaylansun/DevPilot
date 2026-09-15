<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { ChatLineRound, Refresh } from "@element-plus/icons-vue";
import { askKnowledge, getKnowledgeInfo } from "@/api/rag_api";
import { ApiError, errorMessage } from "@/api/http_client";
import type { RagAnswerVO, RagInfoVO } from "@/types/api";

const props = defineProps<{ projectId: string }>();
const route = useRoute();
const info = ref<RagInfoVO | null>(null);
const loading = ref(true);
const loadError = ref("");
const question = ref("");
const sending = ref(false);
const formError = ref("");
type Turn = {
  id: number;
  question: string;
  answer?: RagAnswerVO;
  error?: string;
};
const turns = ref<Turn[]>([]);
let nextId = 1;
let active = true;
let requestController: AbortController | undefined;

async function loadInfo() {
  loading.value = true;
  loadError.value = "";
  try {
    const result = await getKnowledgeInfo(props.projectId);
    if (active) info.value = result;
  } catch (reason) {
    if (active) loadError.value = errorMessage(reason);
  } finally {
    if (active) loading.value = false;
  }
}

async function send() {
  if (sending.value) return;
  const text = question.value.trim();
  if (!text || text.length > 2000) {
    formError.value = "请输入 1～2000 个字符的问题";
    return;
  }
  if (!info.value?.configured || !info.value.ready_documents) return;
  formError.value = "";
  const turn: Turn = { id: nextId++, question: text };
  turns.value.push(turn);
  // 当前阶段只保留最近 20 轮页面记录，不把文档摘录写入浏览器持久存储。
  if (turns.value.length > 20) turns.value.shift();
  sending.value = true;
  requestController = new AbortController();
  try {
    const answer = await askKnowledge(
      props.projectId,
      { question: text },
      requestController.signal,
    );
    if (!active) return;
    const item = turns.value.find((value) => value.id === turn.id);
    if (item) item.answer = answer;
    question.value = "";
  } catch (reason) {
    if (!active) return;
    const item = turns.value.find((value) => value.id === turn.id);
    if (item)
      item.error =
        reason instanceof ApiError && reason.code === "cancelled"
          ? "已停止等待；服务端可能仍在结束当前计算。问题已保留，可再次发送。"
          : errorMessage(reason);
  } finally {
    if (active) sending.value = false;
  }
}

onMounted(loadInfo);
onBeforeUnmount(() => {
  active = false;
  requestController?.abort();
});
</script>

<template>
  <section aria-label="项目知识库问答" class="space-y-6">
    <div class="ui-panel">
      <div
        class="flex flex-wrap items-start justify-between gap-4 max-mobile:flex-col"
      >
        <div class="min-w-0 flex-1">
          <h2 class="m-0 flex items-center gap-2 text-lg">
            <el-icon class="text-brand"><ChatLineRound /></el-icon
            >向项目资料提问
          </h2>
          <p class="ui-muted text-sm leading-7">
            先查找相关原文，再根据资料回答；每条来源都可以展开核对。
          </p>
        </div>
        <el-button
          :icon="Refresh"
          :loading="loading"
          :disabled="sending"
          @click="loadInfo"
          >刷新问答状态</el-button
        >
      </div>
      <p v-if="loadError" class="ui-error" role="alert">{{ loadError }}</p>
      <template v-else-if="info">
        <p
          class="rounded-lg bg-canvas px-4 py-3 text-sm leading-7"
          role="status"
        >
          <template v-if="info.mode === 'mock'"
            >演示模式：只展示检索摘录，不调用大模型，不生成推理回答。</template
          >
          <template v-else
            >真实模型模式：问题和检索到的相关片段会发送给服务器配置的模型服务。回答仅供参考，请核对引用。</template
          >
        </p>
        <p v-if="!info.configured" class="ui-error" role="alert">
          真实问答尚未配置。请在服务器设置 MODEL_NAME、LLM_API_KEY 和
          LLM_BASE_URL 后重新部署；不要在这里填写密钥。
        </p>
        <p v-else-if="!info.ready_documents" class="ui-help">
          还没有已就绪的文档。请先到
          <RouterLink
            :to="{ path: route.path, query: { tab: 'documents' } }"
            class="text-brand underline"
            >知识库上传资料</RouterLink
          >
          ，索引完成后点击“刷新问答状态”。
        </p>
        <p v-else class="ui-help">
          当前有 {{ info.ready_documents }} 份已就绪文档可供检索。
        </p>
      </template>
    </div>

    <div v-if="!turns.length" class="ui-empty">
      <h3>从一个具体问题开始</h3>
      <p>例如：创建订单需要填写哪些信息？库存不足时能否提交订单？</p>
    </div>
    <div v-else class="space-y-5" aria-label="本页问答记录">
      <article
        v-for="turn in turns"
        :key="turn.id"
        class="ui-panel min-w-0"
        :aria-label="'问题：' + turn.question"
      >
        <h3 class="m-0 text-base leading-7 whitespace-pre-wrap wrap-anywhere">
          {{ turn.question }}
        </h3>
        <p v-if="turn.error" class="ui-error mt-4" role="alert">
          {{ turn.error }}
        </p>
        <template v-else-if="turn.answer">
          <p class="mt-4 text-xs text-muted">
            {{ turn.answer.mode === "mock" ? "检索演示" : "AI 回答" }} ·
            {{
              turn.answer.status === "insufficient_evidence"
                ? "资料不足"
                : "附来源引用"
            }}
          </p>
          <!-- 文档和模型输出仅作为纯文本渲染，不执行 HTML 或外部链接。 -->
          <p class="text-sm leading-8 whitespace-pre-wrap wrap-anywhere">
            {{ turn.answer.answer }}
          </p>
          <div
            v-if="turn.answer.sources.length"
            class="mt-5 space-y-3"
            aria-label="回答来源"
          >
            <details
              v-for="source in turn.answer.sources"
              :key="source.source_id"
              class="rounded-lg border border-slate-200 p-4"
            >
              <summary
                class="cursor-pointer text-sm leading-6 text-brand wrap-anywhere"
              >
                [{{ source.source_id }}] {{ source.filename }} · 第
                {{ source.chunk_index + 1 }} 个片段
              </summary>
              <p
                v-if="source.heading"
                class="text-xs leading-6 text-muted wrap-anywhere"
              >
                {{ source.heading }}
              </p>
              <blockquote
                class="mx-0 mb-0 border-l-2 border-brand/30 pl-4 text-sm leading-7 whitespace-pre-wrap wrap-anywhere"
              >
                {{ source.text }}
              </blockquote>
            </details>
          </div>
        </template>
        <p v-else class="ui-help" role="status">
          正在检索资料并准备回答，请稍候……
        </p>
      </article>
    </div>

    <form class="ui-panel" @submit.prevent="send">
      <label for="knowledge-question" class="mb-3 block text-sm font-medium"
        >你想了解什么？</label
      >
      <textarea
        id="knowledge-question"
        v-model="question"
        rows="3"
        maxlength="2000"
        class="w-full resize-y rounded-lg border border-slate-200 p-3 text-sm leading-7 focus:border-brand focus:outline-brand"
        placeholder="请输入关于当前项目文档的问题"
        :disabled="
          sending || loading || !info?.configured || !info?.ready_documents
        "
      />
      <p v-if="formError" class="ui-error" role="alert">{{ formError }}</p>
      <div class="mt-3 flex flex-wrap items-center justify-between gap-3">
        <span class="text-xs text-muted"
          >{{ question.length }} / 2000 · 每次只依据当前问题检索</span
        >
        <div class="flex gap-2">
          <el-button v-if="sending" @click="requestController?.abort()"
            >停止等待</el-button
          >
          <el-button
            native-type="submit"
            type="primary"
            :loading="sending"
            :disabled="
              loading ||
              !info?.configured ||
              !info?.ready_documents ||
              !question.trim()
            "
            >发送问题</el-button
          >
        </div>
      </div>
      <p class="ui-help mt-4">
        当前为单轮问答，页面记录仅临时保留；刷新或离开问答页后会清空。会话持久化与流式输出将在后续阶段接入。
      </p>
    </form>
  </section>
</template>
