<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { decideApproval, getApproval, listApprovals } from "@/api/approval_api";
import { ApiError, errorMessage } from "@/api/http_client";
import { useAuthStore } from "@/stores/auth_store";
import type { ApprovalDecisionQO, ApprovalVO, PlanProposalVO } from "@/types/api";
import type { TraceEvent } from "@/types/stream";
import ApprovalDetails from "@/components/ApprovalDetails.vue";
import RunTrace from "@/components/RunTrace.vue";

const auth = useAuthStore();
const items = ref<ApprovalVO[]>([]), selected = ref<ApprovalVO | null>(null);
const draft = ref<PlanProposalVO | null>(null), editing = ref(false);
const status = ref("pending"), offset = ref(0), total = ref(0);
const loading = ref(false), busy = ref(false), error = ref("");
const trace = ref<TraceEvent[]>([]);
const labels = { pending: "等待审批", processing: "待恢复执行", approved: "已批准", rejected: "已拒绝" };
let active = true, loader: AbortController | undefined, controller: AbortController | undefined;

async function load() {
  if (busy.value) return;
  loader?.abort(); const current = new AbortController(); loader = current;
  loading.value = true;
  try {
    const response = await listApprovals(status.value, offset.value, current.signal);
    if (active && !current.signal.aborted) {
      items.value = response.items; total.value = response.total;
      const id = selected.value?.id;
      if (id) {
        const latest = await getApproval(id, current.signal);
        if (active && !current.signal.aborted && selected.value?.id === id) {
          selected.value = latest;
          if (latest.status !== "pending") editing.value = false;
        }
      }
    }
  } catch (reason) { if (active && !current.signal.aborted) error.value = errorMessage(reason); }
  finally { if (active && !current.signal.aborted) loading.value = false; }
}
function choose(approval: ApprovalVO) {
  if (busy.value) return;
  selected.value = approval;
  draft.value = JSON.parse(JSON.stringify(approval.decision?.proposal ?? approval.plan.proposal));
  editing.value = false; error.value = ""; trace.value = [];
}
function filter() { offset.value = 0; selected.value = null; void load(); }
function page(delta: number) { offset.value += delta; void load(); }
async function decide(action: ApprovalDecisionQO["action"]) {
  const approval = selected.value;
  if (!approval || busy.value) return;
  const body: ApprovalDecisionQO = approval.status === "processing" && approval.decision
    ? approval.decision
    : { action, ...(action === "edit_and_approve" ? { proposal: draft.value! } : {}) };
  const current = new AbortController(); controller = current;
  busy.value = true; error.value = ""; trace.value = [];
  try {
    const result = await decideApproval(approval.id, body, current.signal, event => {
      if (active && !current.signal.aborted && (event.type === "node" || event.type === "tool")) trace.value.push(event);
    });
    if (active && !current.signal.aborted) { selected.value = result; editing.value = false; }
  } catch (reason) {
    if (active) error.value = current.signal.aborted
      ? "已停止等待，已提交的审批决定不会被撤销。请刷新记录确认结果。"
      : errorMessage(reason) + (reason instanceof ApiError && reason.requestId ? `（请求编号：${reason.requestId}）` : "");
  } finally {
    if (active) { busy.value = false; await load(); }
    if (controller === current) controller = undefined;
  }
}
onMounted(load);
onBeforeUnmount(() => { active = false; loader?.abort(); controller?.abort(); });
</script>

<template>
  <section aria-label="审批中心" class="work-panel">
    <div><h1 class="m-0 text-2xl font-semibold">审批工作区</h1><p class="mt-1 mb-0 text-sm text-muted">核对任务、风险与依据，批准后加入项目看板。</p></div>
    <div class="flex flex-wrap items-center gap-3">
      <label for="approval-status" class="text-sm">审批状态</label>
      <select id="approval-status" v-model="status" class="min-h-11 rounded-xl border border-line bg-surface px-3 text-sm" :disabled="busy" @change="filter">
        <option value="pending">等待审批</option><option value="processing">待恢复执行</option><option value="approved">已批准</option><option value="rejected">已拒绝</option><option value="">全部</option>
      </select>
      <el-button :loading="loading" :disabled="busy" @click="load">刷新审批列表</el-button>
      <span class="text-sm text-muted">共 {{ total }} 份方案</span>
    </div>
    <p v-if="error" class="ui-error wrap-anywhere" role="alert">{{ error }}</p>
    <div class="work-fill work-split">
      <section aria-label="审批列表" class="work-scroll space-y-2">
        <p v-if="!items.length && !loading" class="rounded-2xl bg-surface p-6 text-sm leading-7 text-muted">当前没有符合条件的审批方案。</p>
        <button v-for="item in items" :key="item.id" type="button" :disabled="busy" :aria-pressed="selected?.id === item.id" class="ui-interactive block w-full cursor-pointer rounded-xl border border-line bg-surface p-3 text-left disabled:cursor-wait focus-visible:outline-brand" :class="{ 'border-brand!': selected?.id === item.id }" @click="choose(item)">
          <span class="block text-sm font-semibold wrap-anywhere">{{ item.project_name }}</span><span class="mt-1 line-clamp-2 text-xs leading-6 text-muted wrap-anywhere" :title="item.goal">{{ item.goal }}</span><span class="mt-2 block text-xs text-brand">{{ labels[item.status] }}</span>
        </button>
        <div v-if="total > 20" class="flex gap-2"><el-button :disabled="!offset || busy || loading" @click="page(-20)">上一页</el-button><el-button :disabled="offset + 20 >= total || busy || loading" @click="page(20)">下一页</el-button></div>
      </section>
      <section v-if="selected" class="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-xl border border-line bg-surface" aria-label="审阅方案">
        <div class="work-scroll flex-1 p-4">
          <ApprovalDetails :approval="selected" />
          <RunTrace :events="trace" :running="busy" />
          <div v-if="selected.status === 'pending'" class="mt-6 border-t border-line pt-5">
            <el-button :disabled="busy" @click="editing = !editing">{{ editing ? '收起修改' : '修改任务方案' }}</el-button>
            <div v-if="editing && draft" class="mt-4 space-y-5" aria-label="修改任务方案">
              <p class="text-sm leading-7 text-muted">修改任务内容、优先级、验收标准或依赖。提交时会重新检查格式、引用及重复任务。</p>
              <label class="block text-sm">方案摘要<textarea v-model="draft.summary" maxlength="2000" rows="3" :disabled="busy" class="mt-2 block w-full rounded-xl border border-line p-3" /></label>
              <fieldset v-for="task in draft.tasks" :key="task.draft_id" :disabled="busy" class="min-w-0 space-y-3 rounded-xl border border-line p-4">
                <legend class="px-2 text-sm font-medium">{{ task.draft_id }}</legend>
                <label class="block text-sm">任务标题<input v-model="task.title" maxlength="200" class="mt-2 block min-h-11 w-full rounded-lg border border-line px-3" /></label>
                <label class="block text-sm">任务说明<textarea v-model="task.description" maxlength="4000" rows="3" class="mt-2 block w-full rounded-lg border border-line p-3" /></label>
                <label class="block text-sm">优先级<select v-model.number="task.priority" class="ml-3 min-h-11 rounded-lg border border-line px-3"><option v-for="n in 5" :key="n" :value="n">P{{ n }}</option></select></label>
                <label class="block text-sm">验收标准<textarea v-model="task.acceptance_criteria" maxlength="2000" rows="3" class="mt-2 block w-full rounded-lg border border-line p-3" /></label>
                <div><span class="text-sm">前置依赖</span><div class="mt-2 flex flex-wrap gap-3"><label v-for="other in draft.tasks.filter(t => t.draft_id !== task.draft_id)" :key="other.draft_id" class="text-sm"><input v-model="task.dependencies" type="checkbox" :value="other.draft_id" /> {{ other.draft_id }}</label><span v-if="draft.tasks.length === 1" class="text-xs text-muted">无其他任务</span></div></div>
              </fieldset>
            </div>
          </div>
        </div>
        <div v-if="selected.status === 'pending' || selected.status === 'processing' || busy" class="shrink-0 border-t border-line p-3">
          <div v-if="selected.status === 'pending'" class="flex flex-wrap gap-3 [&>.el-button+.el-button]:ml-0">
            <el-button type="primary" :loading="busy" :disabled="busy" @click="decide(editing ? 'edit_and_approve' : 'approve')">{{ editing ? '修改后批准并加入看板' : '批准并加入看板' }}</el-button>
            <el-button :disabled="busy" @click="decide('reject')">拒绝方案</el-button>
          </div>
          <div v-if="selected.status === 'processing'">
            <p class="mt-0 text-xs leading-6 text-muted">审批决定已保存。若执行曾中断，原审批人可继续执行；重复执行不会重复创建任务。</p>
            <el-button v-if="selected.reviewer_id === auth.user?.id" type="primary" :disabled="busy" @click="decide(selected.decision?.action ?? 'approve')">继续执行已保存的决定</el-button>
          </div>
          <el-button v-if="busy" class="mt-4!" @click="controller?.abort()">停止等待</el-button>
        </div>
      </section>
      <p v-else class="m-0 rounded-2xl bg-surface p-8 text-sm leading-7 text-muted">选择一份方案，查看任务、风险及文档依据。</p>
    </div>
  </section>
</template>
