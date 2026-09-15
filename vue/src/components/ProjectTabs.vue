<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import { Grid, Files, ChatDotRound, Aim, Document } from "@element-plus/icons-vue";
const route = useRoute();
const tabs = [
  { label: "项目概览", tab: "", icon: Document },
  { label: "任务看板", tab: "tasks", icon: Grid },
  { label: "知识库", tab: "documents", icon: Files },
  { label: "AI 问答", tab: "chat", icon: ChatDotRound },
  { label: "任务规划", tab: "planning", icon: Aim },
];
const selected = computed(() => Math.max(0, tabs.findIndex((tab) => tab.tab === String(route.query.tab || ""))));
</script>

<template>
  <nav class="relative mb-6 grid w-[570px] max-w-full grid-cols-5 rounded-[14px] bg-raised/80 p-1 max-mobile:mb-4" aria-label="项目功能">
    <span class="pointer-events-none absolute top-1 bottom-1 left-1 w-[calc((100%-8px)/5)] rounded-[10px] bg-white shadow-soft transition-transform duration-300 ease-fluid motion-reduce:transition-none" :style="{ transform: `translateX(${selected * 100}%)` }" aria-hidden="true"></span>
    <RouterLink v-for="(item, index) in tabs" :key="item.tab" :to="{ path: route.path, query: item.tab ? { tab: item.tab } : {} }" class="relative z-10 inline-flex min-h-11 items-center justify-center gap-2 rounded-[10px] px-2 text-sm transition-colors duration-200 max-mobile:px-0.5 max-mobile:text-xs" :class="index === selected ? 'text-ink font-semibold' : 'text-muted hover:text-ink'" :aria-current="index === selected ? 'page' : undefined">
      <el-icon :size="16" class="max-mobile:hidden" aria-hidden="true"><component :is="item.icon" /></el-icon>{{ item.label }}
    </RouterLink>
  </nav>
</template>
