<script setup lang="ts">
import { computed, useId } from "vue";
import { ArrowDown, CircleCheck, Document } from "@element-plus/icons-vue";
import type { PlanResultVO, ToolCallVO } from "@/types/api";

const props = defineProps<{ plan: PlanResultVO; sourcePrefix?: string }>();
const instanceId = useId();
const sourcePrefix = computed(() => `plan-source-${props.sourcePrefix || instanceId}`);

function sourceAnchor(id: number) {
  return `${sourcePrefix.value}-${id}`;
}

function dependencyLabel(id: string) {
  const dependency = props.plan.proposal.tasks.find((task) => task.draft_id === id);
  return dependency ? `${id} · ${dependency.title}` : id;
}

function toolLabel(name: ToolCallVO["name"]) {
  return name === "search_documents" ? "检索项目文档" : "读取任务看板";
}
</script>

<template>
  <div class="min-w-0 space-y-5" aria-label="任务草案内容">
    <!-- 模型、任务和文档内容均通过插值展示为纯文本，不执行 HTML。 -->
    <section aria-label="方案摘要">
      <h3 class="mt-0 mb-3 text-sm font-semibold">方案摘要</h3>
      <p class="m-0 text-sm leading-7 whitespace-pre-wrap wrap-anywhere">{{ plan.proposal.summary }}</p>
    </section>

    <div class="grid min-w-0 gap-3">
      <details class="group min-w-0 rounded-xl bg-raised/55 px-4" aria-label="规划假设">
        <summary class="ui-interactive flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 py-3 text-sm font-medium [&::-webkit-details-marker]:hidden">
          <span>规划假设 <span class="ml-2 font-normal text-muted">{{ plan.proposal.assumptions.length }} 项</span></span>
          <el-icon class="shrink-0 text-muted group-open:rotate-180" aria-hidden="true"><ArrowDown /></el-icon>
        </summary>
        <div class="pb-4">
          <ul v-if="plan.proposal.assumptions.length" class="m-0 space-y-2 pl-5 text-sm leading-7 text-muted">
            <li v-for="(assumption, index) in plan.proposal.assumptions" :key="index" class="whitespace-pre-wrap wrap-anywhere">{{ assumption }}</li>
          </ul>
          <p v-else class="m-0 text-sm leading-7 text-muted">本次未列出额外假设，请自行核对。</p>
        </div>
      </details>
      <details class="group min-w-0 rounded-xl bg-warning/6 px-4" aria-label="风险与待确认项" :open="plan.proposal.risks.length > 0">
        <summary class="ui-interactive flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 py-3 text-sm font-medium text-warning [&::-webkit-details-marker]:hidden">
          <span>风险与待确认项 <span class="ml-2 font-normal">{{ plan.proposal.risks.length }} 项</span></span>
          <el-icon class="shrink-0 group-open:rotate-180" aria-hidden="true"><ArrowDown /></el-icon>
        </summary>
        <div class="pb-4">
          <ul v-if="plan.proposal.risks.length" class="m-0 space-y-2 pl-5 text-sm leading-7 text-muted">
            <li v-for="(risk, index) in plan.proposal.risks" :key="index" class="whitespace-pre-wrap wrap-anywhere">{{ risk }}</li>
          </ul>
          <p v-else class="m-0 text-sm leading-7 text-muted">本次未列出风险，不代表项目没有风险。</p>
        </div>
      </details>
    </div>

    <section class="min-w-0" aria-label="建议任务">
      <div class="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h3 class="m-0 text-base font-semibold">建议任务 · {{ plan.proposal.tasks.length }}</h3>
        <span class="text-xs text-muted">P1 最高，P5 最低</span>
      </div>
      <p v-if="!plan.proposal.tasks.length" class="mt-3 mb-0 text-sm leading-7 text-muted">本次未列出建议任务。</p>
      <div class="divide-y divide-line">
        <article v-for="task in plan.proposal.tasks" :key="task.draft_id" class="min-w-0 py-2" :aria-label="'任务 ' + task.draft_id + '：' + task.title">
          <details class="group min-w-0">
            <summary class="ui-interactive -mx-2 flex min-h-12 cursor-pointer list-none items-start gap-2 rounded-xl px-2 py-2 hover:bg-canvas [&::-webkit-details-marker]:hidden">
              <span class="mt-1 max-w-20 text-xs font-medium text-muted wrap-anywhere">{{ task.draft_id }}</span>
              <h4 class="m-0 min-w-0 flex-1 text-sm font-semibold leading-7 wrap-anywhere">{{ task.title }}</h4>
              <span class="mt-0.5 shrink-0 rounded-full px-2 py-1 text-xs"
                :class="task.priority === 1 ? 'bg-danger/8 text-danger' : task.priority === 2 ? 'bg-warning/8 text-warning' : 'bg-brand/8 text-brand'"
                :aria-label="'优先级 ' + task.priority">P{{ task.priority }}</span>
              <el-icon class="mt-1.5 shrink-0 text-muted group-open:rotate-180" aria-hidden="true"><ArrowDown /></el-icon>
            </summary>
            <div class="pb-5">
              <p class="mt-0 mb-3 text-sm leading-7 text-muted whitespace-pre-wrap wrap-anywhere">{{ task.description }}</p>
              <dl class="m-0 space-y-3 text-sm leading-7">
                <div>
                  <dt class="mb-1 flex items-center gap-2 font-semibold"><el-icon class="text-success" aria-hidden="true"><CircleCheck /></el-icon>验收标准</dt>
                  <dd class="m-0 whitespace-pre-wrap wrap-anywhere">{{ task.acceptance_criteria }}</dd>
                </div>
                <div>
                  <dt class="mb-1 font-semibold">前置依赖</dt>
                  <dd class="m-0 text-muted">
                    <ul v-if="task.dependencies.length" class="m-0 space-y-1 pl-5">
                      <li v-for="id in task.dependencies" :key="id" class="wrap-anywhere">{{ dependencyLabel(id) }}</li>
                    </ul>
                    <span v-else>无前置依赖</span>
                  </dd>
                </div>
                <div>
                  <dt class="mb-1 font-semibold">参考来源</dt>
                  <dd class="m-0 flex flex-wrap gap-x-3 gap-y-1">
                    <a v-for="id in task.source_ids" :key="id" :href="`#${sourceAnchor(id)}`" class="text-brand underline underline-offset-4">依据 [{{ id }}]</a>
                    <span v-if="!task.source_ids.length" class="text-muted">未引用文档，请人工核对</span>
                  </dd>
                </div>
              </dl>
            </div>
          </details>
        </article>
      </div>
    </section>

    <section class="min-w-0 border-t border-line pt-4" aria-label="规划参考来源">
      <h3 class="mt-0 mb-3 flex items-center gap-2 text-sm font-semibold"><el-icon class="text-muted" aria-hidden="true"><Document /></el-icon>参考来源</h3>
      <div v-if="plan.sources.length" class="space-y-2">
        <details v-for="source in plan.sources" :id="sourceAnchor(source.source_id)" :key="source.source_id" :aria-label="'来源 ' + source.source_id" class="min-w-0 scroll-mt-6 rounded-xl bg-canvas px-4" tabindex="-1">
          <summary class="ui-interactive min-h-11 cursor-pointer py-3 text-sm leading-7 text-brand wrap-anywhere">[{{ source.source_id }}] {{ source.filename }} · 第 {{ source.chunk_index + 1 }} 个片段</summary>
          <div class="pb-4">
            <p v-if="source.heading" class="mt-0 mb-2 text-sm leading-7 text-muted wrap-anywhere">{{ source.heading }}</p>
            <blockquote class="m-0 border-l-2 border-brand/25 pl-3 text-sm leading-7 text-muted whitespace-pre-wrap wrap-anywhere">{{ source.text }}</blockquote>
          </div>
        </details>
      </div>
      <p v-else class="m-0 text-sm leading-7 text-muted">本次未返回可引用的文档片段，请人工核对草案。</p>
    </section>

    <details class="min-w-0 border-t border-line pt-2" aria-label="草案读取范围">
      <summary class="ui-interactive min-h-11 cursor-pointer py-3 text-sm font-medium text-muted">已完成的资料与任务读取</summary>
      <ul v-if="plan.tool_calls.length" class="m-0 space-y-2 pl-5 text-sm leading-7 text-muted">
        <li v-for="(call, index) in plan.tool_calls" :key="index" class="wrap-anywhere">{{ toolLabel(call.name) }} · {{ call.status === "empty" ? "已完成，未找到内容" : "已完成" }} · {{ call.item_count }} 项</li>
      </ul>
      <p class="mt-3 mb-0 text-sm leading-7 text-muted wrap-anywhere">生成草案时读取到任务看板共 {{ plan.board_task_count }} 项任务。</p>
    </details>
  </div>
</template>
