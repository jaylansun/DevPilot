<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { FolderOpened, MagicStick, SwitchButton, CircleCheck, ArrowRight } from "@element-plus/icons-vue";
import { useAuthStore } from "@/stores/auth_store";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const pageTitle = computed(() => {
  const tabs: Record<string, string> = { tasks: "任务看板", documents: "知识库", chat: "AI 问答", planning: "任务规划" };
  return route.name === "project" ? tabs[String(route.query.tab)] || "项目概览" : route.meta.title;
});
function signOut() {
  auth.clearSession();
  void router.replace("/login");
}
</script>

<template>
  <div class="flex min-h-dvh max-mobile:block">
    <a class="fixed -top-20 left-4 z-[5000] rounded-lg bg-brand px-5 py-3 text-canvas focus:top-3" href="#main-content">跳到页面内容</a>
    <aside class="sticky top-0 flex h-dvh w-[216px] shrink-0 flex-col border-r border-line/60 bg-sidebar px-4 py-7 max-mobile:static max-mobile:h-auto max-mobile:w-full max-mobile:flex-row max-mobile:flex-wrap max-mobile:items-center max-mobile:gap-4 max-mobile:border-r-0 max-mobile:border-b max-mobile:px-4 max-mobile:py-4">
      <RouterLink :to="auth.homePath" class="inline-flex items-center gap-3 px-2 text-[23px] font-semibold tracking-tight">
        <span class="grid size-9 place-items-center rounded-xl border border-brand/40 bg-brand/10 text-xl text-brand"><MagicStick aria-hidden="true" /></span>
        DevPilot
      </RouterLink>
      <div class="mt-9 mb-7 rounded-xl border border-line/70 bg-surface p-3 max-mobile:hidden">
        <p class="mb-1 text-sm font-medium">个人工作区</p>
        <span class="text-xs text-muted">项目、知识与行动，在此连接</span>
      </div>
      <nav aria-label="主导航" class="max-mobile:order-3 max-mobile:w-full" :class="{ 'max-mobile:hidden': route.name === 'project' }">
        <RouterLink v-if="auth.isMember" to="/projects" class="group flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm transition-colors hover:bg-raised" :class="route.path.startsWith('/projects') ? 'border border-brand/20 bg-brand/10 text-brand' : 'text-muted'">
          <el-icon><FolderOpened /></el-icon>我的项目<el-icon class="ml-auto"><ArrowRight /></el-icon>
        </RouterLink>
        <RouterLink v-else to="/reviewer" class="flex min-h-11 items-center gap-3 rounded-xl border border-brand/20 bg-brand/10 px-3 text-sm text-brand">
          <el-icon><CircleCheck /></el-icon>审批工作区
        </RouterLink>
      </nav>
      <div class="mt-auto px-3 pb-7 pt-10 max-mobile:hidden">
        <div class="mb-4 h-px w-8 bg-brand/60"></div>
        <p class="mb-0 text-xs leading-6 text-muted">把资料变成依据，<br />把目标变成下一步。</p>
      </div>
      <div class="flex min-w-0 items-center gap-2.5 border-t border-line/70 pt-5 max-mobile:ml-auto max-mobile:max-w-[180px] max-mobile:border-0 max-mobile:p-0">
        <span class="grid size-9 shrink-0 place-items-center rounded-full bg-raised text-sm text-brand">{{ auth.user?.username.slice(0, 1).toUpperCase() }}</span>
        <div class="min-w-0 flex-1">
          <strong class="block truncate text-xs font-medium">{{ auth.user?.username }}</strong>
          <span class="mt-1 block text-xs text-muted max-mobile:hidden">{{ auth.isMember ? "项目成员" : "审批人" }}</span>
        </div>
        <el-button text circle aria-label="退出登录" title="退出登录" @click="signOut"><el-icon><SwitchButton /></el-icon></el-button>
      </div>
    </aside>
    <div class="flex min-w-0 flex-1 flex-col">
      <header class="flex min-h-16 items-center justify-between gap-4 border-b border-line/60 px-8 max-mobile:min-h-12 max-mobile:px-4" :class="{ 'max-mobile:hidden': route.name === 'project' }">
        <div class="flex min-w-0 items-center gap-3 text-xs text-muted">
          <span>工作区</span><span aria-hidden="true">/</span><strong class="font-medium text-ink">{{ pageTitle }}</strong>
        </div>
        <span class="rounded-full border border-line px-2.5 py-1 text-xs text-muted max-mobile:hidden">{{ auth.isMember ? "成员工作区" : "审批人工作区" }}</span>
      </header>
      <main id="main-content" tabindex="-1" class="mx-auto flex w-full max-w-[1600px] min-w-0 flex-1 flex-col px-8 py-7 outline-none max-mobile:px-4 max-mobile:py-5">
        <RouterView :key="route.path" />
      </main>
    </div>
  </div>
</template>
