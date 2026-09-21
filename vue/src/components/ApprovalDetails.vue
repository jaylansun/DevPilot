<script setup lang="ts">
import { computed } from "vue";
import type { ApprovalVO } from "@/types/api";
const props = defineProps<{ approval: ApprovalVO }>();
const proposal = computed(() => props.approval.decision?.proposal ?? props.approval.plan.proposal);
const labels = { pending: "等待审批", processing: "决定已记录，待完成执行", approved: "已批准并加入看板", rejected: "已拒绝" };
</script>

<template>
  <section class="min-w-0 space-y-4" aria-label="审批方案详情">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h3 class="m-0 text-lg font-semibold">{{ approval.project_name }}</h3>
      <span class="rounded-full bg-brand/8 px-3 py-1 text-sm text-brand" role="status">{{ labels[approval.status] }}</span>
    </div>
    <p class="m-0 text-sm leading-7 text-muted whitespace-pre-wrap wrap-anywhere">目标：{{ approval.goal }}</p>
    <p v-if="approval.plan.mode === 'mock'" class="m-0 text-sm text-muted">演示草案：请按实际需求核对后审批。</p>
    <p class="whitespace-pre-wrap leading-7 wrap-anywhere">{{ proposal.summary }}</p>
    <details v-if="proposal.assumptions.length || proposal.risks.length" class="rounded-xl bg-raised p-4" open>
      <summary class="cursor-pointer font-medium">假设与风险</summary>
      <ul class="mb-0 space-y-2 pl-5 text-sm leading-7 text-muted">
        <li v-for="(text, i) in proposal.assumptions" :key="'a' + i">假设：{{ text }}</li>
        <li v-for="(text, i) in proposal.risks" :key="'r' + i">风险：{{ text }}</li>
      </ul>
    </details>
    <article v-for="task in proposal.tasks" :key="task.draft_id" class="rounded-xl border border-line p-4">
      <h4 class="mt-0 mb-2 text-base font-semibold wrap-anywhere">{{ task.draft_id }} · {{ task.title }} <span class="text-xs text-muted">P{{ task.priority }}</span></h4>
      <p class="whitespace-pre-wrap text-sm leading-7 wrap-anywhere">{{ task.description }}</p>
      <p class="whitespace-pre-wrap text-sm leading-7 wrap-anywhere">验收：{{ task.acceptance_criteria }}</p>
      <p class="mb-0 text-xs leading-6 text-muted">前置依赖：{{ task.dependencies.join('、') || '无' }} · 来源：{{ task.source_ids.map(id => `[${id}]`).join(' ') || '人工核对' }}</p>
    </article>
    <details class="rounded-xl border border-line p-4">
      <summary class="cursor-pointer text-sm font-medium">查看提交时的文档依据</summary>
      <blockquote v-for="source in approval.plan.sources" :key="source.source_id" class="mx-0 border-l-2 border-brand/30 pl-4 text-sm leading-7 whitespace-pre-wrap wrap-anywhere">[{{ source.source_id }}] {{ source.filename }}<br />{{ source.text }}</blockquote>
    </details>
    <p v-if="approval.status === 'approved'" class="rounded-xl bg-brand/8 p-4 text-sm leading-7 text-brand" role="status">已创建 {{ approval.created_tasks.length }} 项任务。成员可在项目任务看板中查看。</p>
  </section>
</template>
