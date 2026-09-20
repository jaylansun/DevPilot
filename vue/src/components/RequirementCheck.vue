<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import {
  Refresh,
  Search,
  CircleCheck,
  Warning,
  ChatLineRound,
} from "@element-plus/icons-vue";
import { ApiError, errorMessage } from "@/api/http_client";
import { getWorkflowInfo, runWorkflow } from "@/api/workflow_api";
import type {
  WorkflowInfoVO,
  WorkflowRequestQO,
  WorkflowResultVO,
} from "@/types/api";

import RunTrace from "@/components/RunTrace.vue";
import type { TraceEvent } from "@/types/stream";

const trace = ref<TraceEvent[]>([]);
const draft = ref("");
const props = defineProps<{ projectId: string }>();
const route = useRoute();
const info = ref<WorkflowInfoVO | null>(null);
const loading = ref(true);
const loadError = ref("");
const error = ref("");
const requestId = ref("");
const message = ref(
  "对照需求文档，看看现有任务还漏了什么，有哪些需求需要确认？",
);
const intent = ref<NonNullable<WorkflowRequestQO["intent"]>>("auto");
const sending = ref(false);
const result = ref<WorkflowResultVO | null>(null);
const submitted = ref("");
const canRun = computed(() => !loading.value && !!info.value?.configured);
const intentLabels = {
  requirement_check: "需求缺口检查",
  knowledge_question: "文档问答",
  task_lookup: "已有任务查询",
  clarify: "需要明确用途",
};
const statusLabels = { todo: "待办", in_progress: "进行中", done: "已完成" };
let active = true;
let infoController: AbortController | undefined;
let runController: AbortController | undefined;

async function loadInfo() {
  if (sending.value) return;
  infoController?.abort();
  const controller = new AbortController();
  infoController = controller;
  loading.value = true;
  loadError.value = "";
  info.value = null;
  try {
    const response = await getWorkflowInfo(props.projectId, controller.signal);
    if (active && infoController === controller && !controller.signal.aborted)
      info.value = response;
  } catch (reason) {
    if (active && !controller.signal.aborted)
      loadError.value = errorMessage(reason);
  } finally {
    if (active && !controller.signal.aborted) loading.value = false;
  }
}

function clearResult() {
  trace.value = [];
  draft.value = "";
  result.value = null;
  submitted.value = "";
  error.value = "";
  requestId.value = "";
}

function example(
  value: string,
  purpose: NonNullable<WorkflowRequestQO["intent"]>,
) {
  message.value = value;
  intent.value = purpose;
}

function cancel() {
  const controller = runController;
  runController = undefined;
  controller?.abort();
  sending.value = false;
  draft.value = "";
  error.value = "已取消等待，输入已保留。服务端可能仍在结束当前计算。";
  requestId.value = "";
}

async function run() {
  if (sending.value || !canRun.value) return;
  const text = message.value.trim();
  if (!text || text.length > 2000) {
    error.value = "请输入 1～2000 个字符的检查范围或问题";
    return;
  }
  clearResult();
  submitted.value = text;
  sending.value = true;
  const controller = new AbortController();
  runController = controller;
  try {
    const response = await runWorkflow(
      props.projectId,
      { message: text, intent: intent.value },
      controller.signal,
      (event) => {
        if (!active || runController !== controller || controller.signal.aborted) return;
        if (event.type === "token") draft.value += event.text;
        else trace.value.push(event);
      },
    );
    if (active && runController === controller && !controller.signal.aborted)
      result.value = response;
  } catch (reason) {
    if (active && runController === controller) {
      error.value = errorMessage(reason);
      requestId.value =
        reason instanceof ApiError ? (reason.requestId ?? "") : "";
    }
  } finally {
    if (runController === controller) {
      runController = undefined;
      if (active) { sending.value = false; draft.value = ""; }
    }
  }
}

function taskLabel(id: string) {
  const task = result.value?.scope.tasks.find((item) => item.id === id);
  return task ? `${task.title} · ${statusLabels[task.status]}` : id;
}

onMounted(loadInfo);
onBeforeUnmount(() => {
  active = false;
  infoController?.abort();
  runController?.abort();
});
</script>

<template>
  <section aria-label="项目需求检查" class="min-w-0 space-y-5">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 class="m-0 text-xl font-semibold">需求写了，任务安排全了吗？</h2>
        <p class="mt-2 mb-0 text-sm leading-7 text-muted">
          对照文档和看板，找出可能遗漏的需求与需要确认的问题。
        </p>
      </div>
      <el-button
        :icon="Refresh"
        :loading="loading"
        :disabled="sending"
        @click="loadInfo"
        >刷新检查状态</el-button
      >
    </div>
    <div
      class="flex flex-wrap items-center gap-3 text-xs text-muted"
      role="status"
    >
      <span v-if="loading">正在读取检查状态……</span>
      <template v-else-if="info">
        <span class="rounded-full bg-raised px-3 py-2 text-ink">{{
          info.mode === "mock" ? "演示模式" : "真实模型模式"
        }}</span>
        <span>{{ info.ready_documents }} 份就绪文档</span
        ><span>{{ info.task_count }} 项现有任务</span>
        <span>只读 · 本次结果不保存</span>
      </template>
    </div>
    <p v-if="loadError" class="ui-error" role="alert">
      {{ loadError }}，请刷新检查状态后重试。
    </p>
    <p v-if="info && !info.configured" class="ui-error" role="alert">
      真实模式尚未配置模型，请联系部署维护者完成配置后刷新。
    </p>
    <p
      v-if="info?.mode === 'mock'"
      class="rounded-xl bg-raised px-4 py-3 text-sm leading-7 text-muted"
    >
      演示模式会读取真实资料和任务，但不会分析需求覆盖或生成遗漏结论。自动分类采用简单规则，也可以手动选择用途。
    </p>
    <p
      v-if="info && !info.ready_documents"
      class="text-sm leading-7 text-muted"
    >
      还没有就绪文档。需求检查和文档问答需要先到
      <RouterLink
        :to="{ path: route.path, query: { tab: 'documents' } }"
        class="text-brand underline"
        >知识库上传资料</RouterLink
      >；已有任务仍可查询。
    </p>

    <div
      class="grid min-w-0 items-start gap-6 board:grid-cols-[300px_minmax(0,1fr)] desktop:grid-cols-[340px_minmax(0,1fr)]"
    >
      <form
        class="ui-panel min-w-0 space-y-4 board:sticky board:top-6"
        @submit.prevent="run"
      >
        <div>
          <label for="check-intent" class="mb-2 block text-sm font-medium"
            >本次用途</label
          >
          <select
            id="check-intent"
            v-model="intent"
            :disabled="sending"
            class="ui-interactive min-h-11 w-full rounded-lg border border-line bg-white px-3 text-sm"
          >
            <option value="auto">自动识别</option>
            <option value="requirement_check">需求缺口检查</option>
            <option value="knowledge_question">文档问答</option>
            <option value="task_lookup">已有任务查询</option>
          </select>
        </div>
        <div>
          <label for="check-message" class="mb-2 block text-sm font-medium"
            >检查范围或问题</label
          >
          <textarea
            id="check-message"
            v-model="message"
            :disabled="sending"
            rows="5"
            maxlength="2000"
            class="ui-interactive w-full resize-y rounded-xl border border-line bg-white p-3 text-sm leading-7 focus:border-brand focus:outline-brand"
            aria-describedby="check-help"
          />
          <p id="check-help" class="mt-1 text-xs leading-6 text-muted">
            范围越具体，检索越有针对性。最多 2000 字。
          </p>
        </div>
        <div class="flex flex-wrap gap-2" aria-label="检查示例">
          <button
            type="button"
            :disabled="sending"
            class="ui-interactive min-h-10 rounded-lg bg-raised px-3 text-xs text-muted"
            @click="
              example(
                '对照需求文档，看看现有任务还漏了什么，有哪些需求需要确认？',
                'requirement_check',
              )
            "
          >
            检查需求遗漏
          </button>
          <button
            type="button"
            :disabled="sending"
            class="ui-interactive min-h-10 rounded-lg bg-raised px-3 text-xs text-muted"
            @click="example('看板中有哪些进行中的任务？', 'task_lookup')"
          >
            查看进行中任务
          </button>
          <button
            type="button"
            :disabled="sending"
            class="ui-interactive min-h-10 rounded-lg bg-raised px-3 text-xs text-muted"
            @click="example('需求文档中有哪些验收规则？', 'knowledge_question')"
          >
            询问文档规则
          </button>
        </div>
        <el-button
          v-if="!sending"
          native-type="submit"
          type="primary"
          :icon="Search"
          :disabled="!canRun"
          class="min-h-11! w-full"
          >开始检查</el-button
        >
        <el-button v-else class="min-h-11! w-full" @click="cancel"
          >取消等待</el-button
        >
        <p v-if="info?.mode === 'live'" class="text-xs leading-6 text-muted">
          本次输入、检索片段和相关任务内容会发送给已配置的模型服务。
        </p>
        <p class="mb-0 text-xs leading-6 text-muted">
          结果仅供核对，不会创建或修改任务。刷新或离开页面后结果会清空。
        </p>
      </form>

      <div class="min-w-0 space-y-5" aria-live="polite" :aria-busy="sending">
        <p
          v-if="submitted"
          class="m-0 rounded-xl bg-brand/5 px-4 py-3 text-sm leading-7 whitespace-pre-wrap wrap-anywhere"
        >
          <span class="font-medium">本次输入：</span>{{ submitted }}
        </p>
        <RunTrace :events="trace" :running="sending" />
        <div v-if="error" class="ui-error" role="alert">
          <p class="m-0">{{ error }}</p>
          <p v-if="requestId" class="mb-0 text-xs wrap-anywhere">
            请求编号：{{ requestId }}
          </p>
        </div>
        <div
          v-if="sending"
          class="ui-panel text-sm leading-7 text-muted"
          role="status"
        >
          <template v-if="draft">
            <p class="mt-0 text-xs">正在生成，回答与引用尚未校验</p>
            <p class="m-0 whitespace-pre-wrap wrap-anywhere">{{ draft }}</p>
          </template>
          <template v-else>正在处理本次请求，上方会实时显示执行进度；校验完成后展示结果。</template>
        </div>
        <template v-else-if="result">
          <article class="ui-panel min-w-0">
            <div class="flex flex-wrap items-center justify-between gap-3">
              <h3 class="m-0 text-base">{{ intentLabels[result.intent] }}</h3>
              <el-button text @click="clearResult">清空结果</el-button>
            </div>
            <p class="mb-0 text-sm leading-7 whitespace-pre-wrap wrap-anywhere">
              {{ result.answer }}
            </p>
            <p
              v-if="result.status === 'insufficient_evidence'"
              class="mb-0 text-sm text-warning"
            >
              资料不足不等于没有遗漏。
            </p>
          </article>

          <template v-if="result.report">
            <div class="grid grid-cols-3 gap-3 max-mobile:gap-2">
              <div class="rounded-xl bg-success/6 p-3">
                <p class="m-0 text-xs text-muted">已有对应任务</p>
                <strong class="mt-2 block text-2xl text-success">{{
                  result.report.covered.length
                }}</strong>
              </div>
              <div class="rounded-xl bg-warning/6 p-3">
                <p class="m-0 text-xs text-muted">可能遗漏</p>
                <strong class="mt-2 block text-2xl text-warning">{{
                  result.report.missing.length
                }}</strong>
              </div>
              <div class="rounded-xl bg-brand/6 p-3">
                <p class="m-0 text-xs text-muted">需要确认</p>
                <strong class="mt-2 block text-2xl text-brand">{{
                  result.report.questions.length
                }}</strong>
              </div>
            </div>
            <section class="ui-panel min-w-0" aria-label="已有对应任务">
              <h3 class="mt-0 flex items-center gap-2 text-base">
                <el-icon class="text-success"><CircleCheck /></el-icon
                >已有对应任务
              </h3>
              <p class="text-xs leading-6 text-muted">
                有任务代表已安排，不代表功能已实现。
              </p>
              <p
                v-if="!result.report.covered.length"
                class="text-sm text-muted"
              >
                本次未列出有明确对应任务的需求。
              </p>
              <article
                v-for="(item, index) in result.report.covered"
                :key="index"
                class="border-t border-line py-4 text-sm leading-7 wrap-anywhere"
              >
                <h4 class="m-0 text-sm">{{ item.requirement }}</h4>
                <p class="my-2 whitespace-pre-wrap">{{ item.explanation }}</p>
                <ul class="my-2 pl-5 text-muted">
                  <li v-for="id in item.task_ids" :key="id">
                    {{ taskLabel(id) }}
                  </li>
                </ul>
                <a
                  v-for="id in item.source_ids"
                  :key="id"
                  :href="`#check-source-${id}`"
                  class="mr-3 inline-block text-brand underline"
                  >依据 [{{ id }}]</a
                >
              </article>
            </section>
            <section class="ui-panel min-w-0" aria-label="可能遗漏">
              <h3 class="mt-0 flex items-center gap-2 text-base">
                <el-icon class="text-warning"><Warning /></el-icon>可能遗漏
              </h3>
              <p
                v-if="!result.report.missing.length"
                class="mb-0 text-sm leading-7 text-muted"
              >
                {{
                  result.status === "reviewed"
                    ? "在本次已读片段中未发现明显遗漏；这不代表全部需求已完整覆盖。"
                    : "本次资料不足，尚不能判断是否存在遗漏。"
                }}
              </p>
              <article
                v-for="(item, index) in result.report.missing"
                :key="index"
                class="border-t border-line py-4 text-sm leading-7 wrap-anywhere"
              >
                <h4 class="m-0 text-sm">{{ item.requirement }}</h4>
                <p class="my-2 whitespace-pre-wrap">{{ item.explanation }}</p>
                <a
                  v-for="id in item.source_ids"
                  :key="id"
                  :href="`#check-source-${id}`"
                  class="mr-3 inline-block text-brand underline"
                  >依据 [{{ id }}]</a
                >
              </article>
            </section>
            <section class="ui-panel min-w-0" aria-label="需要确认">
              <h3 class="mt-0 flex items-center gap-2 text-base">
                <el-icon class="text-brand"><ChatLineRound /></el-icon>需要确认
              </h3>
              <p
                v-if="!result.report.questions.length"
                class="mb-0 text-sm text-muted"
              >
                本次未列出待确认问题。
              </p>
              <article
                v-for="(item, index) in result.report.questions"
                :key="index"
                class="border-t border-line py-4 text-sm leading-7 wrap-anywhere"
              >
                <h4 class="m-0 text-sm">{{ item.question }}</h4>
                <p class="my-2 whitespace-pre-wrap">{{ item.reason }}</p>
                <a
                  v-for="id in item.source_ids"
                  :key="id"
                  :href="`#check-source-${id}`"
                  class="mr-3 inline-block text-brand underline"
                  >依据 [{{ id }}]</a
                >
              </article>
            </section>
          </template>

          <section
            v-if="result.intent === 'task_lookup'"
            class="ui-panel min-w-0"
            aria-label="查询到的任务"
          >
            <h3 class="mt-0 text-base">匹配任务 · {{ result.tasks.length }}</h3>
            <p v-if="!result.tasks.length" class="mb-0 text-sm text-muted">
              当前读取的看板中没有匹配任务。
            </p>
            <article
              v-for="task in result.tasks"
              :key="task.id"
              class="border-t border-line py-4 text-sm leading-7 wrap-anywhere"
            >
              <h4 class="m-0 text-sm">{{ task.title }}</h4>
              <p class="my-2 text-xs text-muted">
                {{ statusLabels[task.status] }} · P{{ task.priority }}
              </p>
              <p class="my-2 whitespace-pre-wrap">{{ task.description }}</p>
              <p class="my-2 whitespace-pre-wrap">
                验收标准：{{ task.acceptance_criteria || "未填写" }}
              </p>
              <p
                v-if="
                  task.description_truncated ||
                  task.acceptance_criteria_truncated
                "
                class="text-xs text-muted"
              >
                部分内容已截断，请到任务看板查看完整任务。
              </p>
            </article>
          </section>

          <section class="ui-panel min-w-0" aria-label="依据与检查范围">
            <h3 class="mt-0 text-base">依据与检查范围</h3>
            <p class="text-sm leading-7 text-muted">
              {{ result.scope.limitation }}
            </p>
            <p class="text-sm leading-7">
              {{
                result.scope.document_search_performed
                  ? `本次检索到 ${result.sources.length} 个片段`
                  : "本次未检索文档"
              }}
              ·
              {{
                result.scope.board_read
                  ? `已读取 ${result.scope.tasks.length} 项任务`
                  : "本次未读取看板"
              }}
            </p>
            <details class="mb-4 text-sm leading-7">
              <summary class="ui-interactive cursor-pointer text-muted">
                可检索的就绪文档（{{
                  result.scope.ready_documents.length
                }}
                份，不代表逐份已读）
              </summary>
              <ul class="pl-5 wrap-anywhere">
                <li
                  v-for="doc in result.scope.ready_documents"
                  :key="doc.document_id"
                >
                  {{ doc.filename }}
                </li>
              </ul>
            </details>
            <article
              v-for="source in result.sources"
              :id="`check-source-${source.source_id}`"
              :key="source.source_id"
              class="mb-4 scroll-mt-6 rounded-xl bg-raised/70 p-4 text-sm leading-7 wrap-anywhere"
              tabindex="-1"
            >
              <h4 class="m-0 text-sm">
                [{{ source.source_id }}] {{ source.filename }}
              </h4>
              <p class="my-1 text-xs text-muted">
                {{ source.heading || "正文" }} · 片段
                {{ source.chunk_index + 1 }} · 最多 400 字符
              </p>
              <p class="mb-0 whitespace-pre-wrap">{{ source.text }}</p>
            </article>
            <details v-if="result.scope.board_read" class="text-sm leading-7">
              <summary class="ui-interactive cursor-pointer">
                本次读取的看板任务（{{ result.scope.tasks.length }} 项）
              </summary>
              <p
                v-if="result.scope.task_details_truncated"
                class="text-xs text-muted"
              >
                部分说明或验收标准已截断。
              </p>
              <article
                v-for="task in result.scope.tasks"
                :key="task.id"
                class="mt-3 border-t border-line pt-3 wrap-anywhere"
              >
                <h4 class="m-0 text-sm">
                  {{ task.title }} · {{ statusLabels[task.status] }} · P{{
                    task.priority
                  }}
                </h4>
                <p class="my-1 whitespace-pre-wrap">
                  {{ task.description || "未填写说明" }}
                </p>
                <p class="my-1 whitespace-pre-wrap">
                  验收标准：{{ task.acceptance_criteria || "未填写" }}
                </p>
              </article>
            </details>
          </section>
        </template>
        <div
          v-else-if="!sending && !error"
          class="ui-panel text-sm leading-8 text-muted"
        >
          <h3 class="mt-0 text-base text-ink">先核对，再决定下一步</h3>
          <p>已有对应任务：查看哪些需求已安排到看板。</p>
          <p>可能遗漏：查看有文档依据、但缺少对应任务的需求。</p>
          <p>需要确认：发现含糊或矛盾的规则，先把问题说明白。</p>
          <p class="mb-0">没有明显缺口时，可以不新增建议。</p>
        </div>
      </div>
    </div>
  </section>
</template>
