<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import {
  ArrowDown,
  CircleCheck,
  Document,
  List,
  Position,
  Refresh,
} from "@element-plus/icons-vue";
import { getPlanningInfo } from "@/api/planning_api";
import { generateDraft } from "@/api/plan_draft_api";
import PlanDraftList from "@/components/PlanDraftList.vue";
import PlanDraftActions from "@/components/PlanDraftActions.vue";
import { ApiError, errorMessage } from "@/api/http_client";
import type { ApprovalVO, PlanDraftVO, PlanInfoVO, ToolCallVO } from "@/types/api";

import PlanningApprovals from "@/components/PlanningApprovals.vue";
import RunTrace from "@/components/RunTrace.vue";
import type { TraceEvent } from "@/types/stream";

const trace = ref<TraceEvent[]>([]);
const props = defineProps<{ projectId: string }>();
const route = useRoute();
const info = ref<PlanInfoVO | null>(null);
const loading = ref(true);
const loadError = ref("");
const loadRequestId = ref("");
const goal = ref("");
const goalInput = ref<HTMLTextAreaElement | null>(null);
const sending = ref(false);
const approvalSending = ref(false);
const draftBusy = ref(false);
const workspaceTab = ref<"preview" | "approval">("preview");
const formError = ref("");
const formRequestId = ref("");
const selectedDraft = ref<PlanDraftVO | null>(null);
const result = computed(() => selectedDraft.value?.plan ?? null);
const draftEditing = ref(false), draftsRefresh = ref(0), approvalsRefresh = ref(0);
const submittedApproval = ref<ApprovalVO | null>(null);
const submittedGoal = ref("");
const canGenerate = computed(
  () => !draftEditing.value && !approvalSending.value && !draftBusy.value && !loading.value && info.value?.configured && !!info.value.ready_documents,
);
let active = true;
let infoController: AbortController | undefined;
let requestController: AbortController | undefined;

async function loadInfo() {
  if (sending.value || approvalSending.value || draftBusy.value) return;
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
  if (draftEditing.value || approvalSending.value || draftBusy.value) return;
  trace.value = [];
  selectedDraft.value = null;
  submittedGoal.value = "";
  formError.value = "";
  formRequestId.value = "";
}

function useExample(text: string) {
  if (!canGenerate.value || sending.value) return;
  goal.value = text;
  formError.value = "";
  formRequestId.value = "";
  goalInput.value?.focus();
}

function cancelGeneration() {
  const controller = requestController;
  if (!controller) return;
  // 先解除当前请求的归属，迟到响应与旧请求的 finally 都不能覆盖重试。
  requestController = undefined;
  controller.abort();
  sending.value = false;
  formError.value = "已取消生成等待；目标已保留。请先刷新草案记录，确认是否已保存。";
  formRequestId.value = "";
  void nextTick(() => goalInput.value?.focus({ preventScroll: true }));
}

async function generate() {
  workspaceTab.value = "preview";
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
    const response = await generateDraft(
      props.projectId,
      { goal: text },
      controller.signal,
      (event) => {
        if (active && !controller.signal.aborted && requestController === controller && (event.type === "node" || event.type === "tool"))
          trace.value.push(event);
      },
    );
    if (!active || controller.signal.aborted || requestController !== controller)
      return;
    selectedDraft.value = response;
    draftsRefresh.value++;
  } catch (reason) {
    if (!active || requestController !== controller) return;
    formError.value =
      reason instanceof ApiError && reason.code === "cancelled"
        ? "已取消生成等待；目标已保留。请先刷新草案记录，确认是否已保存。"
        : errorMessage(reason);
    formRequestId.value = reason instanceof ApiError ? reason.requestId ?? "" : "";
  } finally {
    if (requestController === controller) {
      if (active) sending.value = false;
      requestController = undefined;
    }
  }
}

function openDraft(draft: PlanDraftVO) {
  if (sending.value || approvalSending.value || draftBusy.value || draftEditing.value) return;
  selectedDraft.value = draft;
  goal.value = draft.goal;
  submittedGoal.value = draft.goal;
  workspaceTab.value = "preview";
  formError.value = "";
  trace.value = [];
}
function updateDraft(draft: PlanDraftVO) {
  selectedDraft.value = draft;
  draftsRefresh.value++;
}
function submitted(approval: ApprovalVO) {
  submittedApproval.value = approval;
  approvalsRefresh.value++;
  workspaceTab.value = "approval";
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
  <section aria-label="项目任务规划" class="work-panel">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div class="min-w-0">
        <h2 class="m-0 text-lg font-semibold text-ink">任务规划</h2>
        <p class="mt-1 mb-0 text-xs leading-6 text-muted">结合项目资料与已有任务，梳理优先级、验收标准和依赖。</p>
      </div>
      <el-button :icon="Refresh" :loading="loading" :disabled="sending || approvalSending || draftBusy" class="ui-interactive min-h-11!" @click="loadInfo">刷新规划状态</el-button>
    </div>

    <div class="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs leading-6 text-muted" role="status" aria-live="polite" aria-atomic="true">
      <template v-if="loading">正在检查项目资料与规划配置……</template>
      <template v-else-if="info">
        <span class="inline-flex items-center gap-2 rounded-full bg-raised px-3 py-1 text-ink">
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
      <p v-if="loadRequestId" class="mt-2 mb-0 text-xs wrap-anywhere">请求编号：{{ loadRequestId }}</p>
      <p class="mt-2 mb-0 text-sm">请检查连接后刷新规划状态。</p>
    </div>
    <div v-if="info && !info.configured" class="ui-error" role="alert">
      真实任务规划尚未配置。请在服务器设置 MODEL_NAME、LLM_API_KEY 和 LLM_BASE_URL 后重新部署；不要在这里填写密钥。
    </div>
    <p v-if="info && !info.ready_documents" class="m-0 text-sm leading-7 text-muted">
      还没有已就绪的文档。请先到
      <RouterLink :to="{ path: route.path, query: { tab: 'documents' } }" class="text-brand underline underline-offset-4">知识库上传资料</RouterLink>
      ，索引完成后点击“刷新规划状态”。
    </p>

    <div class="work-fill work-split">
      <section aria-label="规划对话" class="work-scroll min-w-0 rounded-xl border border-line bg-surface p-4">
        <h3 class="m-0 text-sm font-semibold">规划目标</h3>
        <p class="mt-1 mb-3 text-xs leading-6 text-muted">明确本次范围，生成并保存草案，核对或编辑后提交这一版。</p>
        <div v-if="canGenerate" class="mb-3 flex flex-wrap gap-2" aria-label="目标示例">
          <button type="button" class="ui-interactive min-h-9 rounded-lg bg-raised px-2.5 text-xs text-muted hover:text-brand" @click="useExample('根据项目资料，规划下一阶段的开发任务，明确优先级和验收标准。')">规划下一阶段开发</button>
          <button type="button" class="ui-interactive min-h-9 rounded-lg bg-raised px-2.5 text-xs text-muted hover:text-brand" @click="useExample('结合现有任务，梳理完成项目目标所缺少的工作，并说明任务之间的依赖。')">梳理遗漏与依赖</button>
        </div>
        <p v-if="submittedGoal" aria-label="本次规划目标" class="mb-3 rounded-lg bg-raised p-3 text-xs leading-6 text-muted wrap-anywhere">本次目标：{{ submittedGoal }}</p>
        <RunTrace :events="trace" :running="sending" />
        <form class="mt-3" @submit.prevent="generate">
          <label for="planning-goal" class="mb-2 block text-sm font-medium text-ink">你想完成什么目标？</label>
          <div class="ui-interactive rounded-2xl border border-line bg-surface p-4 shadow-sm shadow-ink/3 focus-within:border-brand focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-brand focus-within:shadow-brand/10">
            <textarea
              id="planning-goal"
              ref="goalInput"
              v-model="goal"
              rows="4"
              maxlength="2000"
              class="block min-h-24 w-full resize-y border-0 bg-transparent p-0 text-sm leading-6 text-ink placeholder:text-muted focus:outline-0 disabled:cursor-not-allowed disabled:opacity-50"
              placeholder="例如：完善下单流程，覆盖表单校验、库存检查和异常处理。"
              :disabled="sending || !canGenerate"
              :aria-invalid="formError === '请输入 1～2000 个字符的目标'"
              :aria-describedby="formError ? 'planning-help planning-error' : 'planning-help'"
            />
            <div class="mt-4 flex flex-wrap items-center justify-between gap-3">
              <span class="text-xs tabular-nums text-muted">{{ goal.length }} / 2000</span>
              <div class="flex flex-wrap gap-2 [&>.el-button+.el-button]:ml-0">
                <el-button v-if="sending" class="ui-interactive min-h-11!" @click="cancelGeneration">取消生成</el-button>
                <el-button native-type="submit" type="primary" :icon="Position" :loading="sending" :disabled="!canGenerate || !goal.trim()" class="ui-interactive min-h-11!">
                  {{ result ? "重新生成草案" : "生成任务草案" }}
                </el-button>
              </div>
            </div>
          </div>
          <div v-if="formError" id="planning-error" class="ui-error ui-enter mt-4" role="alert">
            <p class="m-0 leading-7 wrap-anywhere">{{ formError }}</p>
            <p v-if="formRequestId" class="mt-2 mb-0 text-xs wrap-anywhere">请求编号：{{ formRequestId }}</p>
          </div>
          <div class="mt-2 flex flex-wrap items-center justify-between gap-2">
            <p class="m-0 text-xs leading-6 text-muted">结合最新项目资料生成，结果需要你核对。</p>
            <el-button v-if="result" text :disabled="draftEditing || approvalSending || draftBusy || sending" class="ui-interactive min-h-11!" @click="clearDraft">关闭预览</el-button>
          </div>
          <p id="planning-help" class="mt-3 mb-0 text-xs leading-6 text-muted">
            草案生成后自动保存。核对或编辑后提交这一版，送审不会重新生成。
          </p>
          <p v-if="info" class="mt-2 mb-0 text-xs leading-6 text-muted">
            <template v-if="info.mode === 'mock'">演示模式返回示例草案，不调用真实大模型。请结合项目实际核对内容。</template>
            <template v-else>生成时，目标、相关文档片段与当前任务会发送给服务器配置的模型服务。请核对生成结果与来源。</template>
          </p>
        </form>
        <PlanDraftList :project-id="projectId" :refresh-key="draftsRefresh" :selected-id="selectedDraft?.id" :disabled="sending || approvalSending || draftBusy || draftEditing" @select="openDraft" />
      </section>

      <div class="flex min-h-0 min-w-0 flex-col gap-3">
        <div class="work-view-switch self-start" aria-label="规划结果视图">
          <button type="button" :aria-pressed="workspaceTab === 'preview'" @click="workspaceTab = 'preview'">草案预览</button>
          <button type="button" :aria-pressed="workspaceTab === 'approval'" @click="workspaceTab = 'approval'">审批记录</button>
        </div>
        <div class="work-scroll min-h-0 flex-1">
          <PlanningApprovals v-show="workspaceTab === 'approval'" :project-id="projectId" :refresh-key="approvalsRefresh" :selected-approval="submittedApproval" :disabled="sending || draftEditing || draftBusy" @busy="approvalSending = $event" />
          <div v-show="workspaceTab === 'preview'">
            <section v-if="result" aria-label="任务方案预览" class="ui-enter min-w-0 rounded-xl border border-line bg-surface p-5">
              <header class="mb-4 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 class="m-0 text-lg font-semibold leading-7">任务方案预览</h2>
                  <p class="mt-2 mb-0 text-sm text-muted">{{ result.proposal.tasks.length }} 项建议任务，按优先级逐步推进。</p>
                </div>
                <span class="rounded-full bg-raised px-3 py-1.5 text-xs text-muted">{{ result.mode === "mock" ? "演示草案" : "AI 草案" }} · 已保存</span>
              </header>

              <PlanDraftActions v-if="selectedDraft" :draft="selectedDraft" :disabled="sending || approvalSending" @update="updateDraft" @submitted="submitted" @busy="draftBusy = $event" @editing="draftEditing = $event" />
              <!-- 模型、任务和文档内容均通过插值展示为纯文本，不执行 HTML。 -->
              <div class="mb-4">
                <h3 class="mt-0 mb-3 text-sm font-medium text-muted">方案摘要</h3>
                <p class="m-0 text-sm leading-7 whitespace-pre-wrap wrap-anywhere">{{ result.proposal.summary }}</p>
              </div>

              <div class="mb-4 grid min-w-0 gap-3">
                <details class="group min-w-0 rounded-xl bg-raised/55 px-4" aria-label="规划假设">
                  <summary class="ui-interactive flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 py-3 text-sm font-medium [&::-webkit-details-marker]:hidden">
                    <span>规划假设 <span class="ml-2 font-normal text-muted">{{ result.proposal.assumptions.length }} 项</span></span>
                    <el-icon class="ui-interactive shrink-0 text-muted group-open:rotate-180" aria-hidden="true"><ArrowDown /></el-icon>
                  </summary>
                  <div class="ui-enter pb-4">
                    <ul v-if="result.proposal.assumptions.length" class="m-0 space-y-2 pl-5 text-sm leading-7 text-muted">
                      <li v-for="(assumption, index) in result.proposal.assumptions" :key="index" class="whitespace-pre-wrap wrap-anywhere">{{ assumption }}</li>
                    </ul>
                    <p v-else class="m-0 text-sm leading-7 text-muted">本次未列出额外假设，请自行核对。</p>
                  </div>
                </details>
                <details class="group min-w-0 rounded-xl bg-warning/6 px-4" aria-label="风险与待确认项" :open="result.proposal.risks.length > 0">
                  <summary class="ui-interactive flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 py-3 text-sm font-medium text-warning [&::-webkit-details-marker]:hidden">
                    <span>风险与待确认项 <span class="ml-2 font-normal">{{ result.proposal.risks.length }} 项</span></span>
                    <el-icon class="ui-interactive shrink-0 group-open:rotate-180" aria-hidden="true"><ArrowDown /></el-icon>
                  </summary>
                  <div class="ui-enter pb-4">
                    <ul v-if="result.proposal.risks.length" class="m-0 space-y-2 pl-5 text-sm leading-7 text-muted">
                      <li v-for="(risk, index) in result.proposal.risks" :key="index" class="whitespace-pre-wrap wrap-anywhere">{{ risk }}</li>
                    </ul>
                    <p v-else class="m-0 text-sm leading-7 text-muted">本次未列出风险，不代表项目没有风险。</p>
                  </div>
                </details>
              </div>

              <div class="mb-4">
                <div class="mb-1 flex flex-wrap items-center justify-between gap-2">
                  <h3 class="m-0 text-lg font-semibold">建议任务</h3>
                  <span class="text-xs text-muted">P1 最高，P5 最低</span>
                </div>
                <div class="divide-y divide-line">
                  <article v-for="task in result.proposal.tasks" :key="task.draft_id" class="min-w-0 py-2" :aria-label="'任务 ' + task.draft_id + '：' + task.title">
                    <details class="group">
                      <summary class="ui-interactive -mx-2 flex min-h-12 cursor-pointer list-none items-start gap-3 rounded-xl px-2 py-2 hover:bg-canvas [&::-webkit-details-marker]:hidden">
                        <span class="mt-1 text-xs font-medium text-muted">{{ task.draft_id }}</span>
                        <h4 class="m-0 min-w-0 flex-1 text-base font-semibold leading-7 wrap-anywhere">{{ task.title }}</h4>
                        <span class="mt-0.5 shrink-0 rounded-full px-2 py-1 text-xs"
                          :class="task.priority === 1 ? 'bg-danger/8 text-danger' : task.priority === 2 ? 'bg-warning/8 text-warning' : 'bg-brand/8 text-brand'"
                          :aria-label="'优先级 ' + task.priority">P{{ task.priority }}</span>
                        <el-icon class="ui-interactive mt-1.5 shrink-0 text-muted group-open:rotate-180" aria-hidden="true"><ArrowDown /></el-icon>
                      </summary>
                      <div class="ui-enter pb-6">
                        <p class="mt-0 mb-3 text-sm leading-6 text-muted whitespace-pre-wrap wrap-anywhere">{{ task.description }}</p>
                        <dl class="m-0 space-y-3 text-sm leading-6">
                          <div>
                            <dt class="mb-2 flex items-center gap-2 text-sm font-semibold">
                              <el-icon class="text-success" aria-hidden="true"><CircleCheck /></el-icon>验收标准
                            </dt>
                            <dd class="m-0 whitespace-pre-wrap wrap-anywhere">{{ task.acceptance_criteria }}</dd>
                          </div>
                          <div>
                            <dt class="mb-1 text-sm font-semibold">前置依赖</dt>
                            <dd class="m-0 text-muted">
                              <ul v-if="task.dependencies.length" class="m-0 space-y-1 pl-5">
                                <li v-for="id in task.dependencies" :key="id" class="wrap-anywhere">{{ dependencyLabel(id) }}</li>
                              </ul>
                              <span v-else>无前置依赖</span>
                            </dd>
                          </div>
                          <div>
                            <dt class="mb-1 text-sm font-semibold">参考来源</dt>
                            <dd class="m-0">
                              <span v-if="task.source_ids.length">
                                <span v-for="id in task.source_ids" :key="id" class="mr-2 text-brand">[{{ id }}]</span>
                                <span class="text-sm text-muted">在下方展开核对原文</span>
                              </span>
                              <span v-else class="text-muted">未引用文档，请人工核对</span>
                            </dd>
                          </div>
                        </dl>
                      </div>
                    </details>
                  </article>
                </div>
              </div>

              <div class="border-t border-line pt-6" aria-label="规划参考来源">
                <h3 class="mt-0 mb-3 flex items-center gap-2 text-sm font-semibold"><el-icon class="text-muted" aria-hidden="true"><Document /></el-icon>参考来源</h3>
                <div v-if="result.sources.length" class="space-y-2">
                  <details v-for="source in result.sources" :key="source.source_id" :aria-label="'来源 ' + source.source_id" class="rounded-xl bg-canvas px-4">
                    <summary class="ui-interactive min-h-11 cursor-pointer py-3 text-sm leading-7 text-brand wrap-anywhere">[{{ source.source_id }}] {{ source.filename }} · 第 {{ source.chunk_index + 1 }} 个片段</summary>
                    <div class="ui-enter pb-4">
                      <p v-if="source.heading" class="mt-0 mb-2 text-sm leading-6 text-muted wrap-anywhere">{{ source.heading }}</p>
                      <blockquote class="m-0 border-l-2 border-brand/25 pl-4 text-sm leading-7 text-muted whitespace-pre-wrap wrap-anywhere">{{ source.text }}</blockquote>
                    </div>
                  </details>
                </div>
                <p v-else class="m-0 text-sm leading-7 text-muted">本次未返回可引用的文档片段，请人工核对草案。</p>
              </div>

              <details class="mt-5 border-t border-line pt-2" aria-label="已完成只读工具调用">
                <summary class="ui-interactive min-h-11 cursor-pointer py-3 text-sm font-medium text-muted">已完成只读工具调用</summary>
                <div class="ui-enter">
                  <ul class="m-0 space-y-2 pl-5 text-sm leading-7 text-muted">
                    <li v-for="(call, index) in result.tool_calls" :key="index" class="wrap-anywhere">{{ toolLabel(call.name) }} · {{ call.status === "empty" ? "已完成，未找到内容" : "已完成" }} · {{ call.item_count }} 项</li>
                  </ul>
                  <p class="mt-3 mb-0 text-sm leading-7 text-muted">本次读取到任务看板共 {{ result.board_task_count }} 项任务。以上调用仅用于获取规划信息，草案尚未写入任务看板。</p>
                </div>
              </details>
            </section>

            <div v-else :key="sending ? 'waiting' : 'ready'" aria-label="任务草案工作区" class="ui-enter min-w-0 rounded-2xl bg-surface border border-line px-5 py-6">
              <div class="mb-4 grid size-12 place-items-center rounded-xl bg-raised text-xl text-brand" aria-hidden="true"><el-icon><List /></el-icon></div>
              <h3 class="mt-0 mb-3 text-2xl font-semibold leading-9 text-ink">{{ sending ? "正在整理你的规划" : "任务计划将在这里展开" }}</h3>
              <p class="m-0 max-w-prose text-sm leading-7 text-muted">{{ sending ? "收到完整结果后，这里会展示方案摘要、任务清单和可核对的依据。" : "从一个明确目标开始，把想做的事整理成可以逐步完成的任务。" }}</p>
              <dl class="mt-8 mb-0 space-y-5 text-sm leading-7">
                <div class="flex items-baseline justify-between gap-3"><dt class="font-medium text-ink">方案依据</dt><dd class="m-0 text-right text-muted">摘要、假设与风险</dd></div>
                <div class="flex items-baseline justify-between gap-3"><dt class="font-medium text-ink">执行路径</dt><dd class="m-0 text-right text-muted">任务、验收与依赖</dd></div>
                <div class="flex items-baseline justify-between gap-3"><dt class="font-medium text-ink">核对来源</dt><dd class="m-0 text-right text-muted">文档片段与工具结果</dd></div>
              </dl>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
