<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from "vue";
import { getDraft, submitDraft, updateDraft } from "@/api/plan_draft_api";
import { ApiError, errorMessage } from "@/api/http_client";
import type { ApprovalVO, PlanDraftVO, PlanProposalVO } from "@/types/api";
import type { TraceEvent } from "@/types/stream";
import RunTrace from "./RunTrace.vue";

const props = defineProps<{ draft: PlanDraftVO; disabled: boolean }>();
const emit = defineEmits<{ update: [draft: PlanDraftVO]; submitted: [approval: ApprovalVO]; busy: [value: boolean]; editing: [value: boolean] }>();
const editing = ref(false), busy = ref(false), message = ref(""), conflict = ref(false);
const form = ref<PlanProposalVO | null>(null), trace = ref<TraceEvent[]>([]);
let active = true, controller: AbortController | undefined;
const fieldClass = "rounded-lg border border-line bg-surface px-3 py-2 text-sm leading-6 text-ink focus:outline-2 focus:outline-brand disabled:opacity-60";
const cloneProposal = () => JSON.parse(JSON.stringify(props.draft.plan.proposal)) as PlanProposalVO;
function setEditing(value: boolean) { editing.value = value; emit("editing", value); }
function edit() { form.value = cloneProposal(); message.value = ""; conflict.value = false; setEditing(true); }
function cancelEdit() { form.value = null; message.value = ""; conflict.value = false; setEditing(false); }
function begin() { const current = new AbortController(); controller = current; busy.value = true; emit("busy", true); message.value = ""; return current; }
function finish(current: AbortController) { if (active && controller === current) { busy.value = false; emit("busy", false); controller = undefined; } }
function failure(error: unknown, current: AbortController) {
  if (!active) return;
  message.value = current.signal.aborted ? "已停止等待，服务器可能已保存结果。请刷新草案或重试同一版。" : errorMessage(error);
  if (error instanceof ApiError) {
    if (error.requestId) message.value += `（请求编号：${error.requestId}）`;
    conflict.value = error.code === "draft_version_conflict" || error.code === "draft_already_submitted";
  }
}
async function save() {
  if (!form.value || busy.value || props.disabled || conflict.value) return;
  const current = begin();
  try {
    const draft = await updateDraft(props.draft.project_id, props.draft.id, { version: props.draft.version, proposal: form.value }, current.signal);
    if (active && !current.signal.aborted) { emit("update", draft); cancelEdit(); }
  } catch (error) { failure(error, current); }
  finally { finish(current); }
}
async function reload() {
  if (busy.value || props.disabled) return;
  const current = begin();
  try {
    const draft = await getDraft(props.draft.project_id, props.draft.id, current.signal);
    if (active && !current.signal.aborted) { emit("update", draft); cancelEdit(); }
  } catch (error) { failure(error, current); }
  finally { finish(current); }
}
async function submit() {
  if (busy.value || props.disabled || editing.value) return;
  const current = begin(); trace.value = [];
  try {
    const approval = await submitDraft(props.draft.project_id, props.draft.id, props.draft.version, current.signal, event => {
      if (active && !current.signal.aborted && (event.type === "node" || event.type === "tool")) trace.value.push(event);
    });
    if (active && !current.signal.aborted) {
      emit("update", { ...props.draft, status: "submitted", conversation_id: approval.conversation_id });
      emit("submitted", approval);
    }
  } catch (error) { failure(error, current); }
  finally { finish(current); }
}
watch(() => props.draft.id, () => { cancelEdit(); trace.value = []; });
onBeforeUnmount(() => { active = false; controller?.abort(); });
</script>

<template>
  <section aria-label="草案编辑与送审" class="mb-5 rounded-xl border border-brand/20 bg-brand/3 p-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <p class="m-0 text-sm font-medium">已保存 · 第 {{ draft.version }} 版{{ draft.status === 'submitted' ? ' · 已提交审批' : '' }}</p>
      <div class="flex flex-wrap gap-2 [&>.el-button+.el-button]:ml-0">
        <el-button v-if="draft.status === 'draft' && !editing" :disabled="disabled || busy" @click="edit">编辑草案</el-button>
        <el-button v-if="!editing" type="primary" :disabled="disabled || busy" :loading="busy" @click="submit">{{ draft.status === 'submitted' ? '查看或继续送审' : '提交这一版' }}</el-button>
        <el-button v-if="busy" @click="controller?.abort()">停止等待</el-button>
      </div>
    </div>
    <p class="mb-0 text-xs leading-6 text-muted">{{ editing ? '请先保存修改，再提交审批。' : '送审使用这一版已保存的内容，不会重新生成；批准后才加入任务看板。' }}</p>
    <p v-if="message" role="alert" class="ui-error">{{ message }}</p>
    <el-button v-if="conflict" :disabled="busy || disabled" @click="reload">放弃本地修改并载入最新草案</el-button>
    <el-button v-else-if="message && !editing" :disabled="busy || disabled" @click="reload">刷新草案状态</el-button>
    <RunTrace :events="trace" :running="busy" />
    <form v-if="editing && form" class="mt-4 space-y-4" @submit.prevent="save">
      <label class="block text-sm">方案摘要<textarea v-model="form.summary" required maxlength="2000" rows="3" :disabled="busy" :class="fieldClass" class="mt-2 block w-full" /></label>
      <fieldset v-for="task in form.tasks" :key="task.draft_id" class="m-0 min-w-0 space-y-3 rounded-xl border border-line p-3" :disabled="busy">
        <legend class="px-1 text-sm font-medium">{{ task.draft_id }}</legend>
        <label class="block text-sm">任务标题<input v-model="task.title" required maxlength="200" :class="fieldClass" class="mt-1 block w-full" /></label>
        <label class="block text-sm">优先级<select v-model.number="task.priority" :class="fieldClass" class="mt-1 block w-full"><option v-for="priority in 5" :key="priority" :value="priority">P{{ priority }}{{ priority === 1 ? ' · 最高' : '' }}</option></select></label>
        <label class="block text-sm">任务说明<textarea v-model="task.description" required maxlength="4000" rows="3" :class="fieldClass" class="mt-1 block w-full" /></label>
        <label class="block text-sm">验收标准<textarea v-model="task.acceptance_criteria" required maxlength="2000" rows="3" :class="fieldClass" class="mt-1 block w-full" /></label>
        <p class="m-0 text-xs leading-6 text-muted">依赖：{{ task.dependencies.join('、') || '无' }}；引用：{{ task.source_ids.map(id => `[${id}]`).join(' ') || '无直接引用' }}</p>
      </fieldset>
      <div class="flex flex-wrap gap-2 [&>.el-button+.el-button]:ml-0">
        <el-button type="primary" native-type="submit" :disabled="busy || conflict" :loading="busy">保存修改</el-button>
        <el-button :disabled="busy" @click="cancelEdit">取消编辑</el-button>
      </div>
    </form>
  </section>
</template>
