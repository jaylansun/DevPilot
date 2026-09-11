<script setup lang="ts">
import { useRoute, useRouter } from "vue-router";
import {
  FolderOpened,
  MagicStick,
  SwitchButton,
  CircleCheck,
  ArrowRight,
} from "@element-plus/icons-vue";
import { useAuthStore } from "@/stores/auth_store";
const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
function signOut() {
  auth.clearSession();
  void router.replace("/login");
}
</script>

<template>
  <div class="flex min-h-screen max-mobile:block">
    <a
      class="fixed -top-[60px] left-[15px] z-[5000] bg-white px-5 py-2.5 text-brand focus:top-2.5"
      href="#main-content"
      >跳到页面内容</a
    >
    <aside
      class="sticky top-0 flex h-screen w-[238px] shrink-0 flex-col bg-sidebar px-5 pt-[29px] pb-5 text-[#bfd3d7] max-desktop:w-[212px] max-mobile:static max-mobile:grid max-mobile:h-auto max-mobile:w-full max-mobile:grid-cols-2 max-mobile:items-center max-mobile:gap-x-2.5 max-mobile:gap-y-5 max-mobile:py-[17px] [&>nav]:max-mobile:col-span-full"
    >
      <RouterLink
        :to="auth.homePath"
        class="inline-flex items-center gap-2.5 pl-1.5 text-2xl font-[750] tracking-[-0.7px] text-[#f2fbfa] max-mobile:pl-0 max-mobile:text-[21px]"
        ><span
          class="grid size-[34px] place-items-center rounded-[10px] bg-[#1d9d8e] text-[22px]"
          ><MagicStick /></span
        >DevPilot</RouterLink
      >
      <div
        class="mx-0.5 mt-[38px] mb-[34px] flex gap-[11px] rounded-[10px] border border-[#34505b] px-3 py-3.5 text-xs text-[#e1ecee] [&>div>span]:mt-[5px] [&>div>span]:block [&>div>span]:text-[10px] [&>div>span]:text-[#8fa8b2] max-mobile:hidden"
      >
        <span
          class="grid size-8 place-items-center rounded-[7px] bg-[#304d59] text-base font-[650] text-[#e3edf1]"
          >D</span
        >
        <div>个人工作区<span>把想法变成行动</span></div>
      </div>
      <p
        class="pl-3.5 text-[10px] tracking-[0.1em] text-[#7996a1] max-mobile:hidden"
      >
        工作空间
      </p>
      <nav aria-label="主导航">
        <RouterLink
          v-if="auth.isMember"
          to="/projects"
          class="flex items-center gap-3 rounded-lg p-3.5 text-[13px] [&>.el-icon]:text-lg max-mobile:px-3.5 max-mobile:py-[11px]"
          :class="{
            'bg-[#205049] text-[#c8f4ea]': route.path.startsWith('/projects'),
          }"
          ><el-icon><FolderOpened /></el-icon>我的项目<el-icon
            class="ml-auto text-xs!"
            ><ArrowRight /></el-icon></RouterLink
        ><RouterLink
          v-else
          to="/reviewer"
          class="flex items-center gap-3 rounded-lg p-3.5 text-[13px] [&>.el-icon]:text-lg max-mobile:px-3.5 max-mobile:py-[11px] bg-[#205049] text-[#c8f4ea]"
          ><el-icon><CircleCheck /></el-icon>审批工作区</RouterLink
        >
      </nav>
      <div
        class="mt-auto px-3.5 pt-11 pb-[25px] [&>p]:text-xs [&>p]:leading-[1.9] [&>p]:text-[#86a9ad] max-mobile:hidden"
      >
        <span class="mb-[17px] block h-0.5 w-[26px] bg-[#50837f]"></span>
        <p>先把目标写下来，<br />下一步就会更清楚。</p>
      </div>
      <div
        class="flex items-center gap-2.5 border-t border-[#2c4853] pt-[21px] max-mobile:col-start-2 max-mobile:row-start-1 max-mobile:max-w-[175px] max-mobile:justify-self-end max-mobile:border-0 max-mobile:p-0"
      >
        <div
          class="grid size-[33px] shrink-0 place-items-center rounded-[10px] bg-[#d4e8e2] text-[13px] font-semibold text-[#245b55]"
        >
          {{ auth.user?.username.slice(0, 1).toUpperCase() }}
        </div>
        <div
          class="min-w-0 flex-1 [&>strong]:block [&>strong]:truncate [&>strong]:text-xs [&>strong]:font-medium [&>strong]:text-[#dfedef] [&>span]:mt-[5px] [&>span]:block [&>span]:text-[10px] [&>span]:text-[#89a6ae] max-mobile:[&>strong]:max-w-[100px]"
        >
          <strong>{{ auth.user?.username }}</strong
          ><span>{{ auth.isMember ? "项目成员" : "审批人" }}</span>
        </div>
        <el-button
          text
          circle
          class="text-[#a6c0c9]! hover:bg-[#284955]!"
          aria-label="退出登录"
          title="退出登录"
          @click="signOut"
          ><el-icon><SwitchButton /></el-icon
        ></el-button>
      </div>
    </aside>
    <div class="flex min-w-0 flex-1 flex-col">
      <header
        class="flex min-h-[70px] items-center justify-between gap-4 border-b border-[#e6ebee] bg-white px-[42px] max-desktop:px-7 max-mobile:min-h-[54px] max-mobile:px-5"
      >
        <div
          class="flex gap-[15px] text-xs text-[#81919b] [&>strong]:font-medium [&>strong]:text-[#3b525f]"
        >
          <span>工作区</span><span>/</span
          ><strong>{{
            route.name === "project" && route.query.tab === "tasks"
              ? "任务看板"
              : route.meta.title
          }}</strong>
        </div>
        <div
          class="flex items-center gap-[7px] text-[11px] text-[#788b96] max-mobile:text-[10px]"
        >
          <span class="size-1.5 rounded-full bg-[#29a288]"></span
          >{{ auth.isMember ? "成员工作区" : "审批人工作区" }}
        </div>
      </header>
      <main
        id="main-content"
        class="mx-auto w-full max-w-[1460px] flex-1 px-[42px] pt-[39px] pb-12 max-desktop:px-7 max-desktop:py-8 max-mobile:px-5 max-mobile:py-[27px]"
      >
        <RouterView :key="route.path" />
      </main>
      <footer
        class="flex justify-between gap-[15px] border-t border-[#e6ecef] px-[42px] py-[18px] text-[10px] text-[#99a7af] max-mobile:px-5 max-mobile:text-[9px]"
      >
        DevPilot<span>每一个项目，从清晰的目标开始。</span>
      </footer>
    </div>
  </div>
</template>
