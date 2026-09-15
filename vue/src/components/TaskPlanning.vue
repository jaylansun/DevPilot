<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import { List, Refresh } from "@element-plus/icons-vue";
import { getPlanningInfo, proposeTasks } from "@/api/planning_api";
import { ApiError, errorMessage } from "@/api/http_client";
import type { PlanInfoVO, PlanResultVO, ToolCallVO } from "@/types/api";

const props = defineProps<{ projectId: string }>();
const route = useRoute();
const info = ref<PlanInfoVO | null>(null);
const loading = ref(true);
const loadError = ref("");
const goal = ref("");
const sending = ref(false);
const formError = ref("");
const result = ref<PlanResultVO | null>(null);
const resultGoal = ref("");
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
  info.value = null;
  try {
    const response = await getPlanningInfo(props.projectId, controller.signal);
    if (active && !controller.signal.aborted) info.value = response;
  } catch (reason) {
    if (active && !controller.signal.aborted)
      loadError.value = errorMessage(reason);
  } finally {
    if (active && !controller.signal.aborted) loading.value = false;
  }
}

function clearDraft() {
  result.value = null;
  resultGoal.value = "";
  formError.value = "";
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
  sending.value = true;
  const controller = new AbortController();
  requestController = controller;
  try {
    const response = await proposeTasks(
      props.projectId,
      { goal: text },
      controller.signal,
    );
    if (!active || controller.signal.aborted) return;
    result.value = response;
    resultGoal.value = text;
  } catch (reason) {
    if (!active) return;
    formError.value =
      reason instanceof ApiError && reason.code === "cancelled"
        ? "已取消生成等待；目标已保留，可重新生成。服务端可能仍在结束当前计算。"
        : errorMessage(reason);
  } finally {
    if (active) sending.value = false;
    if (requestController === controller) requestController = undefined;
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
  <section aria-label="项目任务规划" class="min-w-0 space-y-6">
    <div class="ui-panel max-mobile:p-5">
      <div
        class="flex flex-wrap items-start justify-between gap-4 max-mobile:flex-col"
      >
        <div class="min-w-0 flex-1">
          <h2 class="m-0 flex items-center gap-2 text-lg">
            <el-icon class="text-brand"><List /></el-icon>把目标拆成任务草案
          </h2>
          <p class="ui-muted mt-3 mb-0">
            结合当前项目资料与任务看板，梳理优先级、验收标准和任务依赖。
          </p>
        </div>
        <el-button
          :icon="Refresh"
          :loading="loading"
          :disabled="sending"
          @click="loadInfo"
          >刷新规划状态</el-button
        >
      </div>
      <p v-if="loadError" class="ui-error mt-4 mb-0" role="alert">
        {{ loadError }}
      </p>
      <p v-else-if="loading" class="ui-help" role="status">
        正在检查项目资料与规划配置……
      </p>
      <template v-else-if="info">
        <p
          class="mt-5 mb-0 rounded-lg bg-canvas px-4 py-3 text-sm leading-7"
          role="status"
        >
          <template v-if="info.mode === 'mock'"
            >演示模式：返回演示任务草案，不调用真实大模型。请结合项目实际核对内容。</template
          >
          <template v-else
            >真实模型模式：目标、检索到的相关文档片段和当前项目的任务内容会发送给服务器配置的模型服务。生成结果仅供参考，请核对来源。</template
          >
        </p>
        <p v-if="!info.configured" class="ui-error mt-4 mb-0" role="alert">
          真实任务规划尚未配置。请在服务器设置 MODEL_NAME、LLM_API_KEY 和
          LLM_BASE_URL 后重新部署；不要在这里填写密钥。
        </p>
        <p v-if="!info.ready_documents" class="ui-help">
          还没有已就绪的文档。请先到
          <RouterLink
            :to="{ path: route.path, query: { tab: 'documents' } }"
            class="text-brand underline"
            >知识库上传资料</RouterLink
          >
          ，索引完成后点击“刷新规划状态”。
        </p>
        <p v-else class="ui-help">
          当前有 {{ info.ready_documents }} 份已就绪文档，任务看板有
          {{ info.task_count }} 项任务。生成时会读取最新资料与看板信息。
        </p>
      </template>
    </div>

    <form class="ui-panel max-mobile:p-5" @submit.prevent="generate">
      <label for="planning-goal" class="mb-3 block text-sm font-medium"
        >你想完成什么目标？</label
      >
      <textarea
        id="planning-goal"
        v-model="goal"
        rows="4"
        maxlength="2000"
        class="w-full resize-y rounded-lg border border-slate-200 p-3 text-sm leading-7 focus:border-brand focus:outline-brand disabled:bg-canvas"
        placeholder="例如：根据订单规则规划下单流程，覆盖表单校验、库存检查和异常处理"
        :disabled="sending || !canGenerate"
      />
      <div class="mt-3 flex flex-wrap items-center justify-between gap-3">
        <span class="text-xs text-muted">{{ goal.length }} / 2000</span>
        <div class="flex flex-wrap gap-2">
          <el-button v-if="sending" @click="requestController?.abort()"
            >取消生成</el-button
          >
          <el-button v-if="result" @click="clearDraft">清空草案</el-button>
          <el-button
            native-type="submit"
            type="primary"
            :loading="sending"
            :disabled="!canGenerate || !goal.trim()"
            >{{ result ? "重新生成草案" : "生成任务草案" }}</el-button
          >
        </div>
      </div>
      <p v-if="formError" class="ui-error mt-4 mb-0" role="alert">
        {{ formError }}
      </p>
      <p class="ui-help mt-4">
        仅草案预览，未写入任务看板，暂不支持提交审批或持久保存。草案仅临时保留在本页，清空、重新生成、刷新或离开任务规划页后会移除。
      </p>
    </form>

    <div v-if="sending" class="ui-panel max-mobile:p-5" role="status">
      <h3 class="mb-2 text-base">正在准备任务草案……</h3>
      <p class="ui-muted mb-0">
        服务正在读取项目文档和任务看板，并整理任务方案。可以取消等待，目标会保留。
      </p>
    </div>
    <section v-else-if="result" aria-label="任务方案预览" class="space-y-5">
      <div class="ui-panel max-mobile:p-5">
        <div class="mb-5 flex flex-wrap items-center justify-between gap-3">
          <h2 class="m-0 text-lg">任务方案预览</h2>
          <span class="rounded-full bg-brand/10 px-3 py-1 text-xs text-brand">
            {{ result.mode === "mock" ? "演示草案" : "AI 草案" }} · 未保存
          </span>
        </div>
        <div class="mb-5 rounded-lg bg-canvas p-4" aria-label="本次规划目标">
          <p class="mb-2 text-xs text-muted">本次规划目标</p>
          <p class="mb-0 text-sm leading-7 whitespace-pre-wrap wrap-anywhere">
            {{ resultGoal }}
          </p>
        </div>
        <!-- 模型、任务和文档内容均通过插值展示为纯文本，不执行 HTML。 -->
        <h3 class="mb-2 text-sm">方案摘要</h3>
        <p class="mb-0 text-sm leading-8 whitespace-pre-wrap wrap-anywhere">
          {{ result.proposal.summary }}
        </p>
        <div class="mt-5 grid grid-cols-2 gap-5 max-tablet:grid-cols-1">
          <div class="min-w-0 rounded-lg border border-slate-200 p-4">
            <h3 class="mb-2 text-sm">规划假设</h3>
            <ul
              v-if="result.proposal.assumptions.length"
              class="m-0 space-y-2 pl-5 text-sm leading-7"
            >
              <li
                v-for="(assumption, index) in result.proposal.assumptions"
                :key="index"
                class="whitespace-pre-wrap wrap-anywhere"
              >
                {{ assumption }}
              </li>
            </ul>
            <p v-else class="ui-help m-0">本次未列出额外假设，请自行核对。</p>
          </div>
          <div
            class="min-w-0 rounded-lg border border-amber-200 bg-amber-50/40 p-4"
          >
            <h3 class="mb-2 text-sm">风险与待确认项</h3>
            <ul
              v-if="result.proposal.risks.length"
              class="m-0 space-y-2 pl-5 text-sm leading-7"
            >
              <li
                v-for="(risk, index) in result.proposal.risks"
                :key="index"
                class="whitespace-pre-wrap wrap-anywhere"
              >
                {{ risk }}
              </li>
            </ul>
            <p v-else class="ui-help m-0">本次未列出风险，不代表项目没有风险。</p>
          </div>
        </div>
      </div>

      <div class="flex flex-wrap items-center justify-between gap-2 px-1">
        <h3 class="m-0 text-base">
          建议任务 · {{ result.proposal.tasks.length }} 项
        </h3>
        <span class="text-xs text-muted">优先级 1 最高，5 最低</span>
      </div>
      <article
        v-for="task in result.proposal.tasks"
        :key="task.draft_id"
        class="ui-panel max-mobile:p-5"
        :aria-label="'任务 ' + task.draft_id + '：' + task.title"
      >
        <div class="mb-4 flex flex-wrap items-start justify-between gap-3">
          <h3 class="m-0 min-w-0 flex-1 text-base leading-7 wrap-anywhere">
            <span class="mr-2 text-brand">{{ task.draft_id }}</span>{{ task.title }}
          </h3>
          <span
            class="shrink-0 rounded-md px-2.5 py-1 text-xs"
            :class="
              task.priority <= 2
                ? 'bg-amber-50 text-amber-800'
                : 'bg-canvas text-muted'
            "
            >优先级 {{ task.priority }}</span
          >
        </div>
        <p class="mb-5 text-sm leading-7 whitespace-pre-wrap wrap-anywhere">
          {{ task.description }}
        </p>
        <dl class="m-0 space-y-4 text-sm leading-7">
          <div>
            <dt class="font-medium">验收标准</dt>
            <dd class="m-0 mt-1 whitespace-pre-wrap wrap-anywhere">
              {{ task.acceptance_criteria }}
            </dd>
          </div>
          <div>
            <dt class="font-medium">前置依赖</dt>
            <dd class="m-0 mt-1">
              <ul v-if="task.dependencies.length" class="m-0 space-y-1 pl-5">
                <li
                  v-for="id in task.dependencies"
                  :key="id"
                  class="wrap-anywhere"
                >
                  {{ dependencyLabel(id) }}
                </li>
              </ul>
              <span v-else class="text-muted">无前置依赖</span>
            </dd>
          </div>
          <div>
            <dt class="font-medium">参考来源</dt>
            <dd class="m-0 mt-1">
              <span v-if="task.source_ids.length" class="text-brand">
                <span v-for="id in task.source_ids" :key="id" class="mr-2"
                  >[{{ id }}]</span
                >
                <span class="text-xs text-muted">可在下方展开核对原文</span>
              </span>
              <span v-else class="text-muted">未引用文档，请人工核对</span>
            </dd>
          </div>
        </dl>
      </article>

      <div class="ui-panel max-mobile:p-5" aria-label="规划参考来源">
        <h3 class="mb-4 text-base">参考来源</h3>
        <div v-if="result.sources.length" class="space-y-3">
          <details
            v-for="source in result.sources"
            :key="source.source_id"
            :aria-label="'来源 ' + source.source_id"
            class="rounded-lg border border-slate-200 p-4"
          >
            <summary
              class="cursor-pointer text-sm leading-7 text-brand wrap-anywhere"
            >
              [{{ source.source_id }}] {{ source.filename }} · 第
              {{ source.chunk_index + 1 }} 个片段
            </summary>
            <p
              v-if="source.heading"
              class="mt-3 mb-0 text-xs leading-6 text-muted wrap-anywhere"
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
        <p v-else class="ui-help">本次未返回可引用的文档片段，请人工核对草案。</p>
      </div>

      <div class="ui-panel max-mobile:p-5" aria-label="已完成只读工具调用">
        <h3 class="mb-3 text-base">已完成只读工具调用</h3>
        <ul class="m-0 space-y-2 pl-5 text-sm leading-7">
          <li
            v-for="(call, index) in result.tool_calls"
            :key="index"
            class="wrap-anywhere"
          >
            {{ toolLabel(call.name) }} ·
            {{ call.status === "empty" ? "已完成，未找到内容" : "已完成" }} ·
            {{ call.item_count }} 项
          </li>
        </ul>
        <p class="ui-help">
          本次读取到任务看板共 {{ result.board_task_count }} 项任务。以上调用仅用于获取规划信息，草案尚未写入任务看板。
        </p>
      </div>
    </section>
    <div v-else-if="!formError" class="ui-empty">
      <h3>先说清这次要完成什么</h3>
      <p class="mb-0!">写下一个具体目标，查看可核对来源的任务草案。</p>
    </div>
  </section>
</template>
