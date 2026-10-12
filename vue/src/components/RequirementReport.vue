<script setup lang="ts">
import { computed, useId } from "vue";
import { ChatLineRound, CircleCheck, Warning } from "@element-plus/icons-vue";
import type { WorkflowResultVO } from "@/types/api";

const props = defineProps<{
  result: WorkflowResultVO;
  sourcePrefix?: string;
  disabled?: boolean;
}>();
const emit = defineEmits<{ plan: [goal: string] }>();
const instanceId = useId();
const sourcePrefix = computed(() => `check-source-${props.sourcePrefix || instanceId}`);
const statusLabels = { todo: "待办", in_progress: "进行中", done: "已完成" };

function sourceAnchor(id: number) {
  return `${sourcePrefix.value}-${id}`;
}

function taskLabel(id: string) {
  const task = props.result.scope.tasks.find((item) => item.id === id);
  return task ? `${task.title} · ${statusLabels[task.status]}` : id;
}

const gapGoal = computed(() => {
  const missing = props.result.report?.missing ?? [];
  if (!missing.length) return "";
  const heading = "以下缺口来自此前的需求检查，属于历史分析。请结合最新项目资料和已有任务，重新核对缺口依据并生成任务草案，明确优先级、验收标准和依赖，避免重复创建已有任务。\n";
  // 为每一项缺口分配空间，避免长说明挤掉后面的需求；后端最多返回 20 项。
  const itemBudget = Math.floor((2000 - heading.length) / missing.length);
  const lines = missing.map((item, index) => {
    const prefix = `${index + 1}. `;
    // 新规划会重新检索，不能把历史报告的引用编号当作本次来源。
    const requirementText = item.requirement.replace(/\[\s*\d+\s*\]/g, "").trim();
    const explanationText = item.explanation.replace(/\[\s*\d+\s*\]/g, "").trim();
    const requirementBudget = Math.max(1, itemBudget - prefix.length - 4);
    const requirement = requirementText.length > requirementBudget
      ? `${requirementText.slice(0, requirementBudget - 1)}…`
      : requirementText;
    const base = `${prefix}${requirement}`;
    const explanationBudget = itemBudget - base.length - 2;
    const explanation = explanationBudget > 0 ? explanationText.slice(0, explanationBudget) : "";
    return `${base}${explanation ? `：${explanation}` : ""}`;
  });
  return `${heading}${lines.join("\n")}`.slice(0, 2000);
});

function planFromGaps() {
  if (!props.disabled && gapGoal.value) emit("plan", gapGoal.value);
}
</script>

<template>
  <div class="min-w-0 space-y-4" aria-label="需求检查报告">
    <!-- 报告与来源均安全插值为文本，引用只链接到当前报告内的来源。 -->
    <p class="m-0 text-sm leading-7 whitespace-pre-wrap wrap-anywhere">{{ result.answer || result.report?.summary }}</p>
    <p v-if="result.status === 'insufficient_evidence' || result.report?.insufficient_evidence" class="m-0 rounded-lg bg-warning/6 px-3 py-2 text-sm leading-7 text-warning">资料不足不等于没有遗漏。</p>

    <template v-if="result.report">
      <div class="grid min-w-0 grid-cols-3 gap-2" aria-label="检查结果统计">
        <div class="min-w-0 rounded-xl bg-success/6 p-3 max-mobile:px-2">
          <p class="m-0 text-xs leading-5 text-muted wrap-anywhere">已有对应任务</p>
          <strong class="mt-2 block text-xl text-success">{{ result.report.covered.length }}</strong>
        </div>
        <div class="min-w-0 rounded-xl bg-warning/6 p-3 max-mobile:px-2">
          <p class="m-0 text-xs leading-5 text-muted">可能遗漏</p>
          <strong class="mt-2 block text-xl text-warning">{{ result.report.missing.length }}</strong>
        </div>
        <div class="min-w-0 rounded-xl bg-brand/6 p-3 max-mobile:px-2">
          <p class="m-0 text-xs leading-5 text-muted">需要确认</p>
          <strong class="mt-2 block text-xl text-brand">{{ result.report.questions.length }}</strong>
        </div>
      </div>

      <section class="min-w-0 rounded-xl border border-line p-4 max-mobile:p-3" aria-label="已有对应任务">
        <h3 class="mt-0 mb-2 flex items-center gap-2 text-sm font-semibold"><el-icon class="text-success" aria-hidden="true"><CircleCheck /></el-icon>已有对应任务</h3>
        <p class="mb-3 text-xs leading-6 text-muted">有任务代表已安排，不代表功能已实现。</p>
        <p v-if="!result.report.covered.length" class="m-0 text-sm leading-7 text-muted">本次未列出有明确对应任务的需求。</p>
        <article v-for="(item, index) in result.report.covered" :key="index" class="min-w-0 border-t border-line py-3 text-sm leading-7 wrap-anywhere">
          <h4 class="m-0 text-sm font-semibold whitespace-pre-wrap">{{ item.requirement }}</h4>
          <p class="my-2 whitespace-pre-wrap">{{ item.explanation }}</p>
          <ul v-if="item.task_ids.length" class="my-2 pl-5 text-muted"><li v-for="id in item.task_ids" :key="id">{{ taskLabel(id) }}</li></ul>
          <div class="flex flex-wrap gap-x-3 gap-y-1"><a v-for="id in item.source_ids" :key="id" :href="`#${sourceAnchor(id)}`" class="text-brand underline underline-offset-4">依据 [{{ id }}]</a></div>
        </article>
      </section>

      <section class="min-w-0 rounded-xl border border-line p-4 max-mobile:p-3" aria-label="可能遗漏">
        <h3 class="mt-0 mb-3 flex items-center gap-2 text-sm font-semibold"><el-icon class="text-warning" aria-hidden="true"><Warning /></el-icon>可能遗漏</h3>
        <p v-if="!result.report.missing.length" class="m-0 text-sm leading-7 text-muted">{{ result.status === "reviewed" && !result.report.insufficient_evidence ? "在本次已读片段中未发现明显遗漏；这不代表全部需求已完整覆盖。" : "本次资料不足，尚不能判断是否存在遗漏。" }}</p>
        <article v-for="(item, index) in result.report.missing" :key="index" class="min-w-0 border-t border-line py-3 text-sm leading-7 wrap-anywhere">
          <h4 class="m-0 text-sm font-semibold whitespace-pre-wrap">{{ item.requirement }}</h4>
          <p class="my-2 whitespace-pre-wrap">{{ item.explanation }}</p>
          <div class="flex flex-wrap gap-x-3 gap-y-1"><a v-for="id in item.source_ids" :key="id" :href="`#${sourceAnchor(id)}`" class="text-brand underline underline-offset-4">依据 [{{ id }}]</a></div>
        </article>
        <el-button v-if="gapGoal" type="primary" :disabled="disabled" class="ui-interactive mt-3 min-h-11! max-w-full whitespace-normal!" @click="planFromGaps">按缺口生成草案</el-button>
      </section>

      <section class="min-w-0 rounded-xl border border-line p-4 max-mobile:p-3" aria-label="需要确认">
        <h3 class="mt-0 mb-3 flex items-center gap-2 text-sm font-semibold"><el-icon class="text-brand" aria-hidden="true"><ChatLineRound /></el-icon>需要确认</h3>
        <p v-if="!result.report.questions.length" class="m-0 text-sm leading-7 text-muted">本次未列出待确认问题。</p>
        <article v-for="(item, index) in result.report.questions" :key="index" class="min-w-0 border-t border-line py-3 text-sm leading-7 wrap-anywhere">
          <h4 class="m-0 text-sm font-semibold whitespace-pre-wrap">{{ item.question }}</h4>
          <p class="my-2 whitespace-pre-wrap">{{ item.reason }}</p>
          <div class="flex flex-wrap gap-x-3 gap-y-1"><a v-for="id in item.source_ids" :key="id" :href="`#${sourceAnchor(id)}`" class="text-brand underline underline-offset-4">依据 [{{ id }}]</a></div>
        </article>
      </section>
    </template>

    <section v-if="result.intent === 'task_lookup'" class="min-w-0 rounded-xl border border-line p-4 max-mobile:p-3" aria-label="查询到的任务">
      <h3 class="mt-0 mb-3 text-sm font-semibold">匹配任务 · {{ result.tasks.length }}</h3>
      <p v-if="!result.tasks.length" class="m-0 text-sm leading-7 text-muted">当前读取的看板中没有匹配任务。</p>
      <article v-for="task in result.tasks" :key="task.id" class="min-w-0 border-t border-line py-3 text-sm leading-7 wrap-anywhere">
        <h4 class="m-0 text-sm font-semibold">{{ task.title }}</h4>
        <p class="my-2 text-xs text-muted">{{ statusLabels[task.status] }} · P{{ task.priority }}</p>
        <p class="my-2 whitespace-pre-wrap">{{ task.description }}</p>
        <p class="my-2 whitespace-pre-wrap">验收标准：{{ task.acceptance_criteria || "未填写" }}</p>
        <p v-if="task.description_truncated || task.acceptance_criteria_truncated" class="mb-0 text-xs text-muted">部分内容已截断，请到任务看板查看完整任务。</p>
      </article>
    </section>

    <section class="min-w-0 rounded-xl border border-line p-4 max-mobile:p-3" aria-label="依据与检查范围">
      <h3 class="mt-0 mb-3 text-sm font-semibold">依据与检查范围</h3>
      <p class="text-sm leading-7 text-muted whitespace-pre-wrap wrap-anywhere">{{ result.scope.limitation }}</p>
      <p class="text-sm leading-7">{{ result.scope.document_search_performed ? `本次检索到 ${result.sources.length} 个片段` : "本次未检索文档" }} · {{ result.scope.board_read ? `已读取 ${result.scope.tasks.length} 项任务` : "本次未读取看板" }}</p>
      <details class="mb-4 min-w-0 text-sm leading-7">
        <summary class="ui-interactive min-h-11 cursor-pointer text-muted wrap-anywhere">可检索的就绪文档（{{ result.scope.ready_documents.length }} 份，不代表逐份已读）</summary>
        <ul v-if="result.scope.ready_documents.length" class="pl-5 wrap-anywhere"><li v-for="doc in result.scope.ready_documents" :key="doc.document_id">{{ doc.filename }}</li></ul>
        <p v-else class="m-0 text-muted">本次没有就绪文档。</p>
      </details>
      <article v-for="source in result.sources" :id="sourceAnchor(source.source_id)" :key="source.source_id" class="mb-4 min-w-0 scroll-mt-6 rounded-xl bg-raised/70 p-3 text-sm leading-7 wrap-anywhere" tabindex="-1">
        <h4 class="m-0 text-sm font-semibold">[{{ source.source_id }}] {{ source.filename }}</h4>
        <p class="my-1 text-xs text-muted">{{ source.heading || "正文" }} · 片段 {{ source.chunk_index + 1 }} · 最多 400 字符</p>
        <p class="mb-0 whitespace-pre-wrap">{{ source.text }}</p>
      </article>
      <details v-if="result.scope.board_read" class="min-w-0 text-sm leading-7">
        <summary class="ui-interactive min-h-11 cursor-pointer wrap-anywhere">本次读取的看板任务（{{ result.scope.tasks.length }} 项）</summary>
        <p v-if="result.scope.task_details_truncated" class="text-xs text-muted">部分说明或验收标准已截断。</p>
        <article v-for="task in result.scope.tasks" :key="task.id" class="mt-3 min-w-0 border-t border-line pt-3 wrap-anywhere">
          <h4 class="m-0 text-sm font-semibold">{{ task.title }} · {{ statusLabels[task.status] }} · P{{ task.priority }}</h4>
          <p class="my-1 whitespace-pre-wrap">{{ task.description || "未填写说明" }}</p>
          <p class="my-1 whitespace-pre-wrap">验收标准：{{ task.acceptance_criteria || "未填写" }}</p>
        </article>
      </details>
    </section>
  </div>
</template>
