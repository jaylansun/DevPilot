<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { createConversation, listConversations, runConversation } from "@/api/approval_api";
import { ApiError, errorMessage } from "@/api/http_client";
import type { ApprovalVO, ConversationVO } from "@/types/api";
import type { TraceEvent } from "@/types/stream";
import ApprovalDetails from "./ApprovalDetails.vue";
import RunTrace from "./RunTrace.vue";

const props = defineProps<{ projectId: string; goal: string; disabled: boolean }>();
const emit = defineEmits<{ busy: [value: boolean] }>();
const items = ref<ConversationVO[]>([]);
const selected = ref<ApprovalVO | null>(null);
const busy = ref(false), loading = ref(false), offset = ref(0), message = ref("");
const trace = ref<TraceEvent[]>([]);
let active = true, controller: AbortController | undefined, loader: AbortController | undefined;
const labels = { new: "尚未生成", interrupted: "生成中断，可继续", pending: "等待审批", processing: "审批执行中", approved: "已加入看板", rejected: "已拒绝" };

async function load() {
  loader?.abort();
  const current = new AbortController(); loader = current; loading.value = true;
  try {
    const response = await listConversations(props.projectId, offset.value, current.signal);
    if (active && !current.signal.aborted) {
      items.value = response;
      const latest = response.find(item => item.approval?.id === selected.value?.id)?.approval;
      if (latest) selected.value = latest;
    }
  } catch (error) {
    if (active && !current.signal.aborted) message.value = errorMessage(error);
  } finally { if (active && !current.signal.aborted) loading.value = false; }
}
async function submit(id?: string) {
  if (busy.value || (!id && props.disabled)) return;
  if (!id && !props.goal.trim()) { message.value = "请先填写规划目标"; return; }
  busy.value = true; emit("busy", true); message.value = ""; trace.value = []; selected.value = null;
  const current = new AbortController(); controller = current;
  try {
    const conversationId = id ?? (await createConversation(props.projectId, props.goal.trim(), current.signal)).id;
    const approval = await runConversation(conversationId, current.signal, event => {
      if (!active || current.signal.aborted) return;
      if (event.type === "node" || event.type === "tool") trace.value.push(event);
    });
    if (active && !current.signal.aborted) selected.value = approval;
  } catch (error) {
    if (active) message.value = current.signal.aborted
      ? "已停止等待。记录可能已保存，请刷新后继续该记录，避免重复提交。"
      : errorMessage(error) + (error instanceof ApiError && error.requestId ? `（请求编号：${error.requestId}）` : "");
  } finally {
    if (active) { busy.value = false; emit("busy", false); await load(); }
    if (controller === current) controller = undefined;
  }
}
function page(delta: number) { offset.value = Math.max(0, offset.value + delta); void load(); }
onMounted(load);
onBeforeUnmount(() => { active = false; controller?.abort(); loader?.abort(); });
</script>

<template>
  <section aria-label="持久规划与审批" class="min-w-0 rounded-xl border border-line bg-surface p-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div><h3 class="m-0 text-base font-semibold">生成并提交审批</h3><p class="mt-1 mb-0 text-xs leading-6 text-muted">根据当前目标生成并保存新方案，审批人批准后加入看板。</p></div>
      <div class="flex flex-wrap gap-2 [&>.el-button+.el-button]:ml-0">
        <el-button type="primary" :disabled="disabled || !goal.trim() || busy" :loading="busy" @click="submit()">生成并提交审批</el-button>
        <el-button v-if="busy" @click="controller?.abort()">停止等待</el-button>
        <el-button :loading="loading" :disabled="busy" @click="load">刷新审批记录</el-button>
      </div>
    </div>
    <p v-if="message" class="ui-error" role="alert">{{ message }}</p>
    <RunTrace :events="trace" :running="busy" />
    <p v-if="!items.length && !loading" class="text-sm leading-7 text-muted">还没有保存的规划记录。</p>
    <ul class="my-4 max-h-64 list-none space-y-2 overflow-y-auto overscroll-y-contain p-0" aria-label="规划记录">
      <li v-for="item in items" :key="item.id" class="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-raised/60 p-3">
        <div class="min-w-0 flex-1"><p class="m-0 line-clamp-2 text-sm leading-6 wrap-anywhere" :title="item.goal">{{ item.goal }}</p><p class="mt-1 mb-0 text-xs text-muted">{{ labels[item.status] }}</p></div>
        <el-button v-if="item.approval" :disabled="busy" @click="selected = item.approval">查看方案</el-button>
        <el-button v-else :disabled="busy || disabled" @click="submit(item.id)">继续生成并提交</el-button>
      </li>
    </ul>
    <div v-if="offset || items.length === 20" class="flex gap-2">
      <el-button :disabled="!offset || busy || loading" @click="page(-20)">上一页</el-button>
      <el-button :disabled="items.length < 20 || busy || loading" @click="page(20)">下一页</el-button>
    </div>
    <ApprovalDetails v-if="selected" :approval="selected" class="mt-4 border-t border-line pt-4" />
  </section>
</template>
