<script setup lang="ts">
import { computed } from "vue";
import type { StepName, TraceEvent } from "@/types/stream";

const props = defineProps<{ events: TraceEvent[]; running: boolean }>();
const labels: Record<StepName, string> = {
  retrieve_knowledge: "检索相关资料", answer_knowledge: "生成回答", validate_result: "校验结果与依据",
  classify_intent: "识别本次用途", load_lookup_board: "读取任务看板", answer_lookup: "整理匹配任务",
  retrieve_documents: "检索需求文档", load_task_board: "读取任务看板", generate_report: "对照需求与任务",
  clarify: "整理用途说明", draft_proposal: "生成任务草案", search_documents: "检索项目文档",
  read_task_board: "读取任务看板", submit_approval: "保存并提交审批", apply_approval: "执行审批决定",
};
const steps = computed(() => {
  const entries = new Map<string, TraceEvent>();
  for (const event of props.events) entries.set(event.id, event);
  return [...entries.values()];
});
const current = computed(() => steps.value.filter((step) => step.status === "started").map((step) => labels[step.name]).join("、"));
function status(step: TraceEvent) {
  return step.status === "completed" ? "已完成" : step.status === "failed" ? "失败" : props.running ? "进行中" : "已停止";
}
</script>

<template>
  <details v-if="steps.length" class="my-3 rounded-xl border border-line/70 px-3 py-2 text-xs text-muted" aria-label="执行轨迹">
    <summary class="cursor-pointer leading-6 focus-visible:outline-brand">
      {{ running && current ? current + '…' : '执行轨迹 · ' + steps.length + ' 个步骤' }}
    </summary>
    <ol class="mb-1 mt-2 list-none space-y-2 p-0">
      <li v-for="step in steps" :key="step.id" class="flex flex-wrap justify-between gap-2">
        <span>{{ labels[step.name] }}</span>
        <span :class="{ 'text-brand': step.status === 'started' && running }">{{ status(step) }}</span>
      </li>
    </ol>
  </details>
</template>
