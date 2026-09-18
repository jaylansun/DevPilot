<script setup lang="ts">
import { nextTick, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { FolderOpened, SwitchButton, CircleCheck, ArrowLeft, ArrowRight } from "@element-plus/icons-vue";
import BrandMark from "@/components/BrandMark.vue";
import { useAuthStore } from "@/stores/auth_store";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const collapsed = ref(false);
const sidebarToggle = ref<HTMLButtonElement | null>(null);
async function toggleSidebar() {
  collapsed.value = !collapsed.value;
  await nextTick();
  sidebarToggle.value?.focus({ preventScroll: true });
}
function signOut() {
  auth.clearSession();
  void router.replace("/login");
}
</script>

<template>
  <div class="flex min-h-dvh max-mobile:block">
    <a class="fixed -top-20 left-4 z-[5000] rounded-xl bg-brand px-5 py-3 text-white focus:top-3" href="#main-content">跳到页面内容</a>
    <aside class="sticky top-0 flex h-dvh shrink-0 flex-col border-r border-line/70 bg-sidebar px-4 py-6 max-mobile:static max-mobile:h-auto max-mobile:w-full max-mobile:flex-row max-mobile:flex-wrap max-mobile:items-center max-mobile:gap-3 max-mobile:border-r-0 max-mobile:border-b max-mobile:px-4 max-mobile:py-3"
      :class="collapsed ? 'w-20' : 'w-[224px]'">
      <div class="flex items-center justify-between max-mobile:gap-2">
        <RouterLink :to="auth.homePath" aria-label="DevPilot 首页" class="flex min-h-11 items-center gap-2.5 px-1 text-[22px] font-semibold tracking-tight">
          <span class="block size-9 shrink-0 text-brand"><BrandMark /></span><span :class="{ 'mobile:hidden': collapsed }">DevPilot</span>
        </RouterLink>
        <button v-if="!collapsed" ref="sidebarToggle" class="ui-interactive grid size-8 place-items-center rounded-lg text-muted hover:bg-raised hover:text-ink max-mobile:hidden" type="button" aria-label="收起侧栏" title="收起侧栏" @click="toggleSidebar"><ArrowLeft /></button>
      </div>
      <button v-if="collapsed" ref="sidebarToggle" class="ui-interactive mt-4 grid min-h-11 place-items-center rounded-xl text-muted hover:bg-raised max-mobile:hidden" type="button" aria-label="展开侧栏" title="展开侧栏" @click="toggleSidebar"><ArrowRight /></button>
      <div class="mt-10 mb-4 px-3 text-xs font-medium text-muted max-mobile:hidden" :class="{ 'mobile:invisible': collapsed }">工作空间</div>
      <nav aria-label="主导航" class="max-mobile:order-3 max-mobile:w-full" :class="{ 'max-mobile:hidden': route.name === 'project' }">
        <RouterLink v-if="auth.isMember" to="/projects" aria-label="我的项目" title="我的项目" class="ui-interactive flex min-h-11 items-center gap-3 rounded-xl bg-white px-3 text-sm font-medium text-brand shadow-soft" :class="{ 'mobile:justify-center': collapsed }" :aria-current="route.path.startsWith('/projects') ? 'page' : undefined">
          <el-icon :size="19" aria-hidden="true"><FolderOpened /></el-icon><span :class="{ 'mobile:hidden': collapsed }">我的项目</span><span v-if="!collapsed" class="ml-auto size-1.5 rounded-full bg-brand" aria-hidden="true"></span>
        </RouterLink>
        <RouterLink v-else to="/reviewer" aria-label="审批工作区" title="审批工作区" class="ui-interactive flex min-h-11 items-center gap-3 rounded-xl bg-white px-3 text-sm font-medium text-brand shadow-soft">
          <el-icon :size="19" aria-hidden="true"><CircleCheck /></el-icon><span :class="{ 'mobile:hidden': collapsed }">审批工作区</span>
        </RouterLink>
      </nav>
      <div class="mt-auto mb-6 px-3 max-mobile:hidden" :class="{ 'mobile:hidden': collapsed }">
        <p class="mb-1 text-sm font-medium text-ink">你的项目，持续向前。</p><p class="mb-0 text-xs leading-6 text-muted">把想法理清，让下一步更简单。</p>
      </div>
      <div class="flex min-w-0 items-center gap-2.5 border-t border-line/70 pt-5 max-mobile:ml-auto max-mobile:max-w-[160px] max-mobile:border-0 max-mobile:p-0" :class="{ 'mobile:mt-auto mobile:flex-col': collapsed }">
        <span class="grid size-9 shrink-0 place-items-center rounded-full bg-brand/8 text-sm font-medium text-brand">{{ auth.user?.username.slice(0, 1).toUpperCase() }}</span>
        <div class="min-w-0 flex-1" :class="{ 'mobile:hidden': collapsed }"><strong class="block truncate text-[13px] font-medium">{{ auth.user?.username }}</strong><span class="block text-xs text-muted max-mobile:hidden">{{ auth.isMember ? "个人工作区" : "审批工作区" }}</span></div>
        <el-button text circle aria-label="退出登录" title="退出登录" @click="signOut"><el-icon><SwitchButton /></el-icon></el-button>
      </div>
    </aside>
    <div class="flex min-w-0 flex-1 flex-col">
      <header v-if="route.name !== 'project'" class="flex min-h-16 items-center justify-between gap-4 px-10 max-mobile:min-h-12 max-mobile:px-4">
        <div class="flex min-w-0 items-center gap-3 text-[13px] text-muted">
          <span>个人工作区</span><span class="text-muted/60" aria-hidden="true">/</span><span class="text-ink">{{ route.meta.title }}</span>
        </div>
        <span class="text-xs text-muted max-mobile:hidden">DevPilot</span>
      </header>
      <main id="main-content" tabindex="-1" class="mx-auto flex w-full max-w-[1560px] min-w-0 flex-1 flex-col outline-none max-mobile:px-4 max-mobile:pb-4 max-mobile:pt-3"
        :class="route.name === 'project' ? 'px-6 pb-4 pt-4' : 'px-10 pb-8 pt-5'">
        <RouterView v-slot="{ Component }"><Transition name="page" mode="out-in"><component :is="Component" :key="route.path" /></Transition></RouterView>
      </main>
    </div>
  </div>
</template>
