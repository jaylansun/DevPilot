<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { getDraft } from "@/api/plan_draft_api";
import { getApproval, getConversation } from "@/api/approval_api";
import { errorMessage } from "@/api/http_client";
import PlanDraftActions from "./PlanDraftActions.vue";
import PlanPreview from "./PlanPreview.vue";
import RequirementReport from "./RequirementReport.vue";
import ApprovalDetails from "./ApprovalDetails.vue";
import type { ApprovalVO, ChatArtifactVO, PlanDraftVO } from "@/types/api";

const props = defineProps<{ projectId: string; artifact: ChatArtifactVO; initialDraft?: PlanDraftVO; disabled: boolean; sourcePrefix: string }>();
const emit = defineEmits<{ update: [draft: PlanDraftVO]; submitted: [approval: ApprovalVO]; busy: [value: boolean]; editing: [value: boolean]; plan: [goal: string] }>();
const savedDraft = ref<PlanDraftVO | null>(null);
const approval = ref<ApprovalVO | null>(null);
const loading = ref(false), actionBusy = ref(false), editing = ref(false), message = ref("");
const busy = computed(() => loading.value || actionBusy.value);
const plan = computed(() => props.artifact.type === "task_plan" ? savedDraft.value?.plan ?? props.artifact.result : null);
let active = true, requestId = 0, controller: AbortController | undefined;
watch(busy, value => emit("busy", value));
watch(editing, value => emit("editing", value));

async function load() {
  controller?.abort();
  const version = ++requestId;
  const current = new AbortController(); controller = current;
  savedDraft.value = null; approval.value = null; message.value = "";
  loading.value = false;
  if (props.artifact.type !== "task_plan" || !props.artifact.draft_id) return;
  loading.value = true;
  try {
    const result = props.initialDraft?.id === props.artifact.draft_id
      ? props.initialDraft : await getDraft(props.projectId, props.artifact.draft_id, current.signal);
    if (!active || version !== requestId || current.signal.aborted) return;
    savedDraft.value = result; emit("update", result);
    if (result.conversation_id) {
      const record = await getConversation(result.conversation_id, current.signal);
      const match = record.approval;
      if (match && active && version === requestId && !current.signal.aborted) approval.value = match;
    }
  } catch (reason) {
    if (active && version === requestId && !current.signal.aborted) message.value = errorMessage(reason);
  } finally { if (active && version === requestId) loading.value = false; }
}
function updated(draft: PlanDraftVO) { savedDraft.value = draft; emit("update", draft); }
function submitted(value: ApprovalVO) { approval.value = value; emit("submitted", value); }
async function refreshApproval() {
  if (!approval.value || busy.value || props.disabled) return;
  const current = new AbortController(); controller = current;
  const version = ++requestId;
  loading.value = true; message.value = "";
  try {
    const result = await getApproval(approval.value.id, current.signal);
    if (active && version === requestId && !current.signal.aborted) approval.value = result;
  } catch (reason) { if (active && version === requestId && !current.signal.aborted) message.value = errorMessage(reason); }
  finally { if (active && version === requestId) loading.value = false; }
}
watch(() => props.artifact, () => { editing.value = false; void load(); }, { immediate: true });
onBeforeUnmount(() => { active = false; ++requestId; controller?.abort(); emit("busy", false); emit("editing", false); });
</script>

<template>
  <div class="min-w-0 space-y-4">
    <template v-if="artifact.type === 'task_plan' && plan">
      <p class="m-0 text-sm leading-7 text-muted whitespace-pre-wrap wrap-anywhere">目标：{{ artifact.goal }}</p>
      <p v-if="loading" class="m-0 text-xs text-muted" role="status">正在读取最新草案状态……</p>
      <div v-if="message" class="ui-error" role="alert"><p class="m-0">{{ message }}</p><el-button :disabled="busy || disabled" text @click="load">刷新草案状态</el-button></div>
      <PlanDraftActions v-if="savedDraft" :draft="savedDraft" :disabled="disabled || loading" @update="updated" @submitted="submitted" @busy="actionBusy = $event" @editing="editing = $event" />
      <p v-else-if="!loading" class="m-0 rounded-xl bg-raised p-3 text-xs leading-6 text-muted">{{ artifact.draft_id ? '当前展示生成时的草案，载入已保存版本后可以编辑和送审。' : '这份草案尚未保存，暂不能编辑或送审。' }}</p>
      <div v-if="approval" class="rounded-xl border border-brand/20 p-3">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-2"><h3 class="m-0 text-sm font-semibold">审批状态</h3><el-button text :loading="loading" :disabled="busy || disabled || editing" @click="refreshApproval">刷新审批状态</el-button></div>
        <ApprovalDetails :approval="approval" />
      </div>
      <PlanPreview v-else :plan="plan" :source-prefix="sourcePrefix" />
    </template>
    <RequirementReport v-else-if="artifact.type === 'requirement_check'" :result="artifact.result" :source-prefix="sourcePrefix" :disabled="disabled" @plan="emit('plan', $event)" />
  </div>
</template>
