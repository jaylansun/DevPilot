<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import {
  ChatLineRound,
  CircleCheck,
  Document,
  List,
  Position,
  Refresh,
} from "@element-plus/icons-vue";
import { getPlanningInfo, proposeTasks } from "@/api/planning_api";
import { ApiError, errorMessage } from "@/api/http_client";
import type { PlanInfoVO, PlanResultVO, ToolCallVO } from "@/types/api";
import AiPresence from "@/components/AiPresence.vue";

const props = defineProps<{ projectId: string }>();
const route = useRoute();
const info = ref<PlanInfoVO | null>(null);
const loading = ref(true);
const loadError = ref("");
const loadRequestId = ref("");
const goal = ref("");
const goalInput = ref<HTMLTextAreaElement | null>(null);
const sending = ref(false);
const formError = ref("");
const formRequestId = ref("");
const result = ref<PlanResultVO | null>(null);
const submittedGoal = ref("");
const canGenerate = computed(
  () => !loading.value && info.value?.configured && !!info.value.ready_documents,
);
let active = true;
let infoController: AbortController | undefined;
let requestController: AbortController | undefined;

async function loadInfo() {
  if (sending.value) return;
  infoController?.abort();
  const controller = new AbortController();
  infoController = controller;
  loading.value = true;
  loadError.value = "";
  loadRequestId.value = "";
  info.value = null;
  try {
    const response = await getPlanningInfo(props.projectId, controller.signal);
    if (active && !controller.signal.aborted) info.value = response;
  } catch (reason) {
    if (active && !controller.signal.aborted) {
      loadError.value = errorMessage(reason);
      loadRequestId.value = reason instanceof ApiError ? reason.requestId ?? "" : "";
    }
  } finally {
    if (active && !controller.signal.aborted) loading.value = false;
  }
}

function clearDraft() {
  result.value = null;
  submittedGoal.value = "";
  formError.value = "";
  formRequestId.value = "";
}

function useExample(text: string) {
  goal.value = text;
  goalInput.value?.focus();
}

function cancelGeneration() {
  const controller = requestController;
  if (!controller) return;
  // 先解除当前请求的归属，迟到响应与旧请求的 finally 都不能覆盖重试。
  requestController = undefined;
  controller.abort();
  sending.value = false;
  formError.value = "已取消生成等待；目标已保留，可重新生成。服务端可能仍在结束当前计算。";
  formRequestId.value = "";
}

async function generate() {
  if (sending.value) return;
  const text = goal.value.trim();
  if (!text || text.length > 2000) {
    formError.value = "请输入 1～2000 个字符的目标";
    return;
  }
  if (!canGenerate.value) return;
  // 新请求开始时移除上一份草案，避免把旧结果误认为本次生成结果。
  clearDraft();
  submittedGoal.value = text;
  sending.value = true;
  const controller = new AbortController();
  requestController = controller;
  try {
    const response = await proposeTasks(
      props.projectId,
      { goal: text },
      controller.signal,
    );
    if (!active || controller.signal.aborted || requestController !== controller)
      return;
    result.value = response;
  } catch (reason) {
    if (!active || requestController !== controller) return;
    formError.value =
      reason instanceof ApiError && reason.code === "cancelled"
        ? "已取消生成等待；目标已保留，可重新生成。服务端可能仍在结束当前计算。"
        : errorMessage(reason);
    formRequestId.value = reason instanceof ApiError ? reason.requestId ?? "" : "";
  } finally {
    if (requestController === controller) {
      if (active) sending.value = false;
      requestController = undefined;
    }
  }
}

function toolLabel(name: ToolCallVO["name"]) {
  return name === "search_documents" ? "检索项目文档" : "读取任务看板";
}

function dependencyLabel(id: string) {
  const dependency = result.value?.proposal.tasks.find(
    (task) => task.draft_id === id,
  );
  return dependency ? `${id} · ${dependency.title}` : id;
}

onMounted(loadInfo);
onBeforeUnmount(() => {
  active = false;
  infoController?.abort();
  requestController?.abort();
});
</script>

<template>
  <section aria-label="项目任务规划" class="min-w-0 space-y-5">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0">
        <h2 class="m-0 text-xl font-semibold text-ink">把目标变成可执行的计划</h2>
        <p class="mt-2 mb-0 text-sm leading-6 text-muted">
          结合项目资料与已有任务，梳理优先级、验收标准和依赖。
        </p>
      </div>
      <el-button
        :icon="Refresh"
        :loading="loading"
        :disabled="sending"
        class="min-h-11!"
        @click="loadInfo"
      >刷新规划状态</el-button>
    </div>

    <div
      class="flex flex-wrap items-center gap-x-5 gap-y-2 border-y border-line py-3 text-sm leading-6 text-muted"
      role="status"
      aria-live="polite"
      aria-atomic="true"
    >
      <template v-if="loading">正在检查项目资料与规划配置……</template>
      <template v-else-if="info">
        <span class="inline-flex items-center gap-2 text-ink">
          <span class="size-1.5 rounded-full bg-brand" aria-hidden="true" />
          {{ info.mode === "mock" ? "演示模式" : "真实模型模式" }}
        </span>
        <span>{{ info.ready_documents }} 份就绪文档</span>
        <span>看板已有 {{ info.task_count }} 项任务</span>
      </template>
      <span v-else>规划状态暂不可用</span>
    </div>

    <div v-if="loadError" class="ui-error" role="alert">
      <p class="m-0">{{ loadError }}</p>
      <p v-if="loadRequestId" class="mt-2 mb-0 text-xs wrap-anywhere">
        请求编号：{{ loadRequestId }}
      </p>
      <p class="mt-2 mb-0 text-sm">请检查连接后刷新规划状态。</p>
    </div>
    <div v-if="info && !info.configured" class="ui-error" role="alert">
      真实任务规划尚未配置。请在服务器设置 MODEL_NAME、LLM_API_KEY 和
      LLM_BASE_URL 后重新部署；不要在这里填写密钥。
    </div>
    <p v-if="info && !info.ready_documents" class="m-0 text-sm leading-7 text-muted">
      还没有已就绪的文档。请先到
      <RouterLink
        :to="{ path: route.path, query: { tab: 'documents' } }"
        class="text-brand underline underline-offset-4"
      >知识库上传资料</RouterLink>
      ，索引完成后点击“刷新规划状态”。
    </p>

    <div class="grid min-w-0 items-start gap-5 board:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
      <section
        aria-label="规划对话"
        class="min-w-0 overflow-hidden rounded-2xl border border-line bg-surface board:sticky board:top-6"
      >
        <div class="flex items-center gap-3 border-b border-line px-5 py-4 mobile:px-6">
          <el-icon class="text-brand" aria-hidden="true"><ChatLineRound /></el-icon>
          <h3 class="m-0 text-sm font-semibold">与 DevPilot 一起规划</h3>
        </div>

        <div class="space-y-6 px-5 py-6 mobile:px-6">
          <div v-if="!submittedGoal" class="min-w-0">
            <div class="flex min-w-0 items-center gap-3">
              <div class="size-32 shrink-0"><AiPresence /></div>
              <div class="min-w-0">
                <h3 class="m-0 text-lg font-semibold leading-8">这次，你想推进什么？</h3>
                <p class="mt-2 mb-0 text-sm leading-7 text-muted">把目标、范围与关键约束告诉我。</p>
              </div>
            </div>
            <div v-if="canGenerate" class="mt-5 flex flex-wrap gap-2" aria-label="目标示例">
              <button
                type="button"
                class="min-h-11 cursor-pointer rounded-lg border border-line bg-raised px-3 py-2 text-left text-xs leading-5 text-muted transition-colors hover:border-brand/60 hover:text-ink"
                @click="useExample('根据项目资料，规划下一阶段的开发任务，明确优先级和验收标准。')"
              >规划下一阶段开发</button>
              <button
                type="button"
                class="min-h-11 cursor-pointer rounded-lg border border-line bg-raised px-3 py-2 text-left text-xs leading-5 text-muted transition-colors hover:border-brand/60 hover:text-ink"
                @click="useExample('结合现有任务，梳理完成项目目标所缺少的工作，并说明任务之间的依赖。')"
              >梳理遗漏与依赖</button>
            </div>
          </div>

          <template v-else>
            <div aria-label="本次规划目标" class="ml-4 min-w-0">
              <p class="mt-0 mb-2 text-right text-xs text-muted">你</p>
              <p class="m-0 rounded-2xl rounded-tr-sm border border-brand/25 bg-brand/10 px-4 py-3 text-sm leading-7 whitespace-pre-wrap wrap-anywhere">{{ submittedGoal }}</p>
            </div>
            <div class="flex min-w-0 items-start gap-3">
              <span class="flex size-8 shrink-0 items-center justify-center rounded-lg bg-raised text-brand" aria-hidden="true">
                <el-icon><Position /></el-icon>
              </span>
              <div class="min-w-0 flex-1">
                <p class="mt-1 mb-2 text-xs font-medium text-muted">DevPilot</p>
                <div aria-live="polite" aria-atomic="true">
                  <template v-if="sending">
                    <p class="m-0 text-sm font-medium leading-7">正在准备任务草案……</p>
                    <p class="mt-2 mb-0 text-sm leading-7 text-muted">
                      已发送规划请求，正在等待完整方案。返回后会一并展示文档引用与工具结果。
                    </p>
                    <p class="mt-3 mb-0 text-xs leading-6 text-muted">可以取消等待，目标会保留。</p>
                  </template>
                  <template v-else-if="result">
                    <p class="m-0 text-sm leading-7">
                      已整理出 {{ result.proposal.tasks.length }} 项建议任务。先核对假设与风险，再查看每项任务的验收标准。
                    </p>
                    <p class="mt-2 mb-0 text-xs leading-6 text-muted">
                      你可以修改下方目标，重新生成一份草案。
                    </p>
                  </template>
                  <p v-else class="m-0 text-sm leading-7 text-muted">
                    本次尚未生成草案。目标已保留，准备好后可以再次生成。
                  </p>
                </div>
              </div>
            </div>
          </template>
        </div>

        <form class="border-t border-line bg-raised/40 p-5 mobile:p-6" @submit.prevent="generate">
          <label for="planning-goal" class="mb-3 block text-sm font-medium text-ink">你想完成什么目标？</label>
          <textarea
            id="planning-goal"
            ref="goalInput"
            v-model="goal"
            rows="4"
            maxlength="2000"
            class="block min-h-32 w-full resize-y rounded-xl border border-line bg-canvas px-4 py-3 text-base leading-7 text-ink placeholder:text-muted focus:border-brand focus:outline-2 focus:outline-offset-2 focus:outline-brand disabled:cursor-not-allowed disabled:opacity-50"
            placeholder="例如：完善下单流程，覆盖表单校验、库存检查和异常处理。"
            :disabled="sending || !canGenerate"
            :aria-invalid="formError === '请输入 1～2000 个字符的目标'"
            :aria-describedby="formError ? 'planning-help planning-error' : 'planning-help'"
          />
          <div class="mt-3 flex flex-wrap items-center justify-between gap-3">
            <span class="text-xs tabular-nums text-muted">{{ goal.length }} / 2000</span>
            <div class="flex flex-wrap gap-2 [&>.el-button+.el-button]:ml-0">
              <el-button v-if="sending" class="min-h-11!" @click="cancelGeneration">取消生成</el-button>
              <el-button v-if="result" class="min-h-11!" @click="clearDraft">清空草案</el-button>
              <el-button
                native-type="submit"
                type="primary"
                :icon="Position"
                :loading="sending"
                :disabled="!canGenerate || !goal.trim()"
                class="min-h-11!"
              >{{ result ? "重新生成草案" : "生成任务草案" }}</el-button>
            </div>
          </div>
          <div v-if="formError" id="planning-error" class="ui-error mt-4" role="alert">
            <p class="m-0 leading-7 wrap-anywhere">{{ formError }}</p>
            <p v-if="formRequestId" class="mt-2 mb-0 text-xs wrap-anywhere">请求编号：{{ formRequestId }}</p>
          </div>
          <p id="planning-help" class="mt-4 mb-0 text-xs leading-6 text-muted">
            仅生成临时草案，暂不支持保存、提交审批或加入看板。清空、重新生成、刷新或离开后移除。
          </p>
          <p v-if="info" class="mt-3 mb-0 text-xs leading-6 text-muted">
            <template v-if="info.mode === 'mock'">演示模式返回示例草案，不调用真实大模型。请结合项目实际核对内容。</template>
            <template v-else>生成时，目标、相关文档片段与当前任务会发送给服务器配置的模型服务。请核对生成结果与来源。</template>
          </p>
        </form>
      </section>

      <section v-if="result" aria-label="任务方案预览" class="min-w-0 overflow-hidden rounded-2xl border border-line bg-surface">
        <div class="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4 mobile:px-6">
          <h2 class="m-0 flex items-center gap-2 text-sm font-semibold">
            <el-icon class="text-brand" aria-hidden="true"><List /></el-icon>
            任务方案预览
          </h2>
          <span class="rounded-md border border-line bg-raised px-2.5 py-1 text-xs text-muted">
            {{ result.mode === "mock" ? "演示草案" : "AI 草案" }} · 未保存
          </span>
        </div>

        <div class="space-y-7 px-5 py-6 mobile:px-6">
          <!-- 模型、任务和文档内容均通过插值展示为纯文本，不执行 HTML。 -->
          <div>
            <h3 class="mt-0 mb-3 text-xs font-medium text-muted">方案摘要</h3>
            <p class="m-0 text-base leading-8 whitespace-pre-wrap wrap-anywhere">{{ result.proposal.summary }}</p>
          </div>
          <div class="grid min-w-0 gap-5 border-y border-line py-5 desktop:grid-cols-2">
            <div class="min-w-0">
              <h3 class="mt-0 mb-3 text-sm font-semibold">规划假设</h3>
              <ul v-if="result.proposal.assumptions.length" class="m-0 space-y-2 pl-4 text-sm leading-7 text-muted">
                <li v-for="(assumption, index) in result.proposal.assumptions" :key="index" class="whitespace-pre-wrap wrap-anywhere">{{ assumption }}</li>
              </ul>
              <p v-else class="m-0 text-sm leading-7 text-muted">本次未列出额外假设，请自行核对。</p>
            </div>
            <div class="min-w-0">
              <h3 class="mt-0 mb-3 text-sm font-semibold">风险与待确认项</h3>
              <ul v-if="result.proposal.risks.length" class="m-0 space-y-2 pl-4 text-sm leading-7 text-muted">
                <li v-for="(risk, index) in result.proposal.risks" :key="index" class="whitespace-pre-wrap wrap-anywhere">{{ risk }}</li>
              </ul>
              <p v-else class="m-0 text-sm leading-7 text-muted">本次未列出风险，不代表项目没有风险。</p>
            </div>
          </div>

          <div>
            <div class="mb-5 flex flex-wrap items-center justify-between gap-2">
              <h3 class="m-0 text-base font-semibold">建议任务 <span class="ml-1 text-muted">{{ result.proposal.tasks.length }}</span></h3>
              <span class="text-xs text-muted">P1 最高，P5 最低</span>
            </div>
            <div class="space-y-4">
              <article
                v-for="task in result.proposal.tasks"
                :key="task.draft_id"
                class="min-w-0 rounded-xl border border-line bg-canvas/60 p-4 mobile:p-5"
                :aria-label="'任务 ' + task.draft_id + '：' + task.title"
              >
                <div class="mb-3 flex min-w-0 flex-wrap items-start gap-3">
                  <span class="mt-0.5 rounded-md border border-line bg-raised px-2 py-1 text-xs font-medium text-brand">{{ task.draft_id }}</span>
                  <h4 class="m-0 min-w-0 flex-1 text-base font-semibold leading-7 wrap-anywhere">{{ task.title }}</h4>
                  <span
                    class="shrink-0 rounded-md border px-2 py-1 text-xs"
                    :class="task.priority <= 2 ? 'border-brand/40 bg-brand/10 text-brand' : 'border-line bg-raised text-muted'"
                    :aria-label="'优先级 ' + task.priority"
                  >P{{ task.priority }}</span>
                </div>
                <p class="mt-0 mb-5 text-sm leading-7 text-muted whitespace-pre-wrap wrap-anywhere">{{ task.description }}</p>
                <dl class="m-0 space-y-4 text-sm leading-7">
                  <div>
                    <dt class="mb-1 flex items-center gap-2 font-medium">
                      <el-icon class="text-brand" aria-hidden="true"><CircleCheck /></el-icon>
                      验收标准
                    </dt>
                    <dd class="m-0 whitespace-pre-wrap wrap-anywhere">{{ task.acceptance_criteria }}</dd>
                  </div>
                  <div class="border-t border-line pt-3">
                    <dt class="font-medium">前置依赖</dt>
                    <dd class="m-0 mt-1 text-muted">
                      <ul v-if="task.dependencies.length" class="m-0 space-y-1 pl-4">
                        <li v-for="id in task.dependencies" :key="id" class="wrap-anywhere">{{ dependencyLabel(id) }}</li>
                      </ul>
                      <span v-else>无前置依赖</span>
                    </dd>
                  </div>
                  <div>
                    <dt class="font-medium">参考来源</dt>
                    <dd class="m-0 mt-1">
                      <span v-if="task.source_ids.length">
                        <span v-for="id in task.source_ids" :key="id" class="mr-2 text-brand">[{{ id }}]</span>
                        <span class="text-xs text-muted">可在下方展开核对原文</span>
                      </span>
                      <span v-else class="text-muted">未引用文档，请人工核对</span>
                    </dd>
                  </div>
                </dl>
              </article>
            </div>
          </div>

          <div class="border-t border-line pt-6" aria-label="规划参考来源">
            <h3 class="mt-0 mb-4 flex items-center gap-2 text-sm font-semibold">
              <el-icon class="text-brand" aria-hidden="true"><Document /></el-icon>
              参考来源
            </h3>
            <div v-if="result.sources.length" class="space-y-3">
              <details
                v-for="source in result.sources"
                :key="source.source_id"
                :aria-label="'来源 ' + source.source_id"
                class="rounded-lg border border-line bg-canvas/60 px-4"
              >
                <summary class="min-h-11 cursor-pointer py-3 text-sm leading-7 text-brand wrap-anywhere">
                  [{{ source.source_id }}] {{ source.filename }} · 第 {{ source.chunk_index + 1 }} 个片段
                </summary>
                <p v-if="source.heading" class="mt-0 mb-2 text-xs leading-6 text-muted wrap-anywhere">{{ source.heading }}</p>
                <blockquote class="mx-0 mt-0 mb-4 border-l-2 border-brand/40 pl-4 text-sm leading-7 text-muted whitespace-pre-wrap wrap-anywhere">{{ source.text }}</blockquote>
              </details>
            </div>
            <p v-else class="m-0 text-sm leading-7 text-muted">本次未返回可引用的文档片段，请人工核对草案。</p>
          </div>

          <div class="border-t border-line pt-6" aria-label="已完成只读工具调用">
            <h3 class="mt-0 mb-3 text-sm font-semibold">已完成只读工具调用</h3>
            <ul class="m-0 space-y-2 pl-4 text-xs leading-7 text-muted">
              <li v-for="(call, index) in result.tool_calls" :key="index" class="wrap-anywhere">
                {{ toolLabel(call.name) }} · {{ call.status === "empty" ? "已完成，未找到内容" : "已完成" }} · {{ call.item_count }} 项
              </li>
            </ul>
            <p class="mt-3 mb-0 text-xs leading-6 text-muted">
              本次读取到任务看板共 {{ result.board_task_count }} 项任务。以上调用仅用于获取规划信息，草案尚未写入任务看板。
            </p>
          </div>
        </div>
      </section>

      <div v-else aria-label="任务草案工作区" class="min-w-0 rounded-2xl border border-dashed border-line bg-surface/50 px-5 py-8 mobile:px-7 board:min-h-96">
        <div class="mb-8 flex items-center gap-2 text-muted">
          <el-icon aria-hidden="true"><List /></el-icon>
          <h3 class="m-0 text-sm font-medium">任务草案</h3>
        </div>
        <h3 class="mt-0 mb-3 text-lg font-semibold text-ink">
          {{ sending ? "正在整理你的规划" : "任务计划将在这里展开" }}
        </h3>
        <p class="m-0 max-w-prose text-sm leading-7 text-muted">
          {{ sending ? "收到完整结果后，这里会展示方案摘要、任务清单和可核对的依据。" : "从一个明确目标开始，查看有优先级、有验收标准、有来源的任务草案。" }}
        </p>
        <dl class="mt-7 mb-0 divide-y divide-line text-sm">
          <div class="flex items-baseline justify-between gap-3 py-3">
            <dt class="text-ink">方案依据</dt><dd class="m-0 text-right text-muted">摘要、假设与风险</dd>
          </div>
          <div class="flex items-baseline justify-between gap-3 py-3">
            <dt class="text-ink">执行路径</dt><dd class="m-0 text-right text-muted">任务、验收与依赖</dd>
          </div>
          <div class="flex items-baseline justify-between gap-3 py-3">
            <dt class="text-ink">核对来源</dt><dd class="m-0 text-right text-muted">文档片段与工具结果</dd>
          </div>
        </dl>
      </div>
    </div>
  </section>
</template>
