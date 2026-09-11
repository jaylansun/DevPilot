<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowRight, MagicStick, Lock, User } from "@element-plus/icons-vue";
import { useAuthStore } from "@/stores/auth_store";
import { errorMessage } from "@/api/http_client";
import { safeRedirect } from "@/router";

const auth = useAuthStore();
const route = useRoute();
const router = useRouter();
const username = ref("");
const password = ref("");
const busy = ref(false);
const error = ref("");

function enterWorkspace() {
  return router.replace(
    auth.isMember
      ? safeRedirect(route.query.redirect, auth.homePath)
      : auth.homePath,
  );
}

async function signIn() {
  if (busy.value) return;
  error.value = "";
  if (!username.value.trim() || !password.value) {
    error.value = "请输入用户名和密码";
    return;
  }
  busy.value = true;
  try {
    await auth.signIn({
      username: username.value.trim(),
      password: password.value,
    });
    password.value = "";
    await enterWorkspace();
  } catch (reason) {
    error.value = errorMessage(reason);
  } finally {
    busy.value = false;
  }
}

async function restoreSession() {
  busy.value = true;
  error.value = "";
  try {
    await auth.restore();
    if (auth.user) await enterWorkspace();
  } catch (reason) {
    error.value = errorMessage(reason);
  } finally {
    busy.value = false;
  }
}

onMounted(() => {
  if (route.query.reason === "connection")
    error.value = "暂时无法验证登录状态，请重试或重新登录";
  else if (auth.token) void restoreSession();
});
</script>

<template>
  <main class="grid min-h-screen grid-cols-[1.08fr_1fr] max-tablet:grid-cols-1">
    <section
      class="flex flex-col bg-[#102e37] bg-[radial-gradient(ellipse_at_0_80%,#205b59_0,transparent_60%)] px-[9%] py-[46px] text-white max-desktop:p-9 max-tablet:p-7 wide:px-[14%]"
      aria-label="DevPilot 简介"
    >
      <a
        class="inline-flex items-center gap-2.5 text-2xl font-[750] tracking-[-0.7px] text-[#f2fbfa]"
        href="/login"
        ><span
          class="grid size-[34px] place-items-center rounded-[10px] bg-[#1d9d8e] text-[22px]"
          ><MagicStick /></span
        >DevPilot<span
          class="ml-1.5 border-l border-[#426068] pl-4 text-xs font-normal tracking-normal text-[#adcbc9] max-mobile:hidden"
          >项目协作助手</span
        ></a
      >
      <div
        class="my-auto max-w-[500px] pt-[68px] pb-11 [&>.ui-eyebrow]:text-[#7ccebf] [&>h1]:mt-4 [&>h1]:mb-[22px] [&>h1]:text-[clamp(29px,3.3vw,48px)] [&>h1]:font-[650] [&>h1]:leading-[1.5] [&>h1]:tracking-[-0.035em] max-tablet:pt-9 max-tablet:pb-2.5 max-tablet:[&>h1]:text-[32px]"
      >
        <p class="ui-eyebrow">从一个想法，开始协作</p>
        <h1>让每一个想法，<br />都有清晰的下一步。</h1>
        <p class="text-[15px] leading-[1.9] text-[#adc6c9] max-tablet:hidden">
          把需求整理到一起，让项目有方向，<br />让每一项工作都有着落。
        </p>
        <div
          class="mt-9 rounded-[14px] border border-[#3d6369] bg-white/[0.027] px-6 pt-[23px] pb-2 [&>p]:mt-3 [&>p]:mb-5 [&>p]:text-xs [&>p]:text-[#abc4c5] max-tablet:hidden"
          aria-label="项目与任务示例"
        >
          <div class="flex items-center gap-2.5 text-[15px] font-semibold">
            <span class="size-[9px] rounded-[3px] bg-[#6cd2bc]"></span
            >餐厅外卖网站<span
              class="ml-auto rounded border border-[#577277] px-2 py-[3px] text-[10px] font-normal text-[#b9cccc]"
              >示例</span
            >
          </div>
          <p>让顾客在线点餐，让餐厅轻松接单。</p>
          <div
            class="flex items-center gap-3 border-t border-[#ffffff13] py-4 text-xs text-[#daece9] [&>span:last-child]:ml-auto [&>span:last-child]:text-[11px] [&>span:last-child]:text-[#9bbab9]"
          >
            <span
              class="size-[17px] shrink-0 rounded-full border border-[#75cbb6] bg-[#75cbb6] text-center text-[#102e37] leading-4"
              >✓</span
            >梳理菜单与点餐流程<span>已完成</span>
          </div>
          <div
            class="flex items-center gap-3 border-t border-[#ffffff13] py-4 text-xs text-[#daece9] [&>span:last-child]:ml-auto [&>span:last-child]:text-[11px] [&>span:last-child]:text-[#9bbab9]"
          >
            <span
              class="size-[17px] shrink-0 rounded-full border-4 border-[#86c2d9]"
            ></span
            >设计购物车页面<span>进行中</span>
          </div>
          <div
            class="flex items-center gap-3 border-t border-[#ffffff13] py-4 text-xs text-[#daece9] [&>span:last-child]:ml-auto [&>span:last-child]:text-[11px] [&>span:last-child]:text-[#9bbab9]"
          >
            <span
              class="size-[17px] shrink-0 rounded-full border border-[#668b8b]"
            ></span
            >接入订单支付<span>待办</span>
          </div>
        </div>
      </div>
      <p
        class="mt-5 mb-0 text-[11px] tracking-[0.18em] text-[#8bb3b3] max-tablet:hidden"
      >
        想法 · 需求 · 行动
      </p>
    </section>
    <section
      class="flex flex-col items-center justify-center bg-white px-10 pt-16 pb-7 max-tablet:px-6 max-tablet:pt-8 max-tablet:pb-6"
    >
      <div
        class="m-auto w-[min(386px,100%)] py-8 [&>h2]:mb-[9px] [&>h2]:text-[28px] [&>h2]:tracking-[-0.025em] max-tablet:max-w-[460px]"
      >
        <p class="ui-eyebrow">欢迎回来</p>
        <h2>登录你的工作区</h2>
        <p class="ui-muted mb-8">继续推进你的项目。</p>
        <el-alert
          v-if="route.query.reason === 'expired'"
          title="登录已失效，请重新登录"
          type="warning"
          :closable="false"
          show-icon
        />
        <form class="mt-6" @submit.prevent="signIn">
          <div class="ui-field">
            <label for="login-username">用户名</label
            ><el-input
              id="login-username"
              v-model="username"
              :prefix-icon="User"
              placeholder="请输入用户名"
              autocomplete="username"
              maxlength="64"
              size="large"
              :disabled="busy"
            />
          </div>
          <div class="ui-field">
            <label for="login-password">密码</label
            ><el-input
              id="login-password"
              v-model="password"
              :prefix-icon="Lock"
              type="password"
              show-password
              placeholder="请输入密码"
              autocomplete="current-password"
              maxlength="128"
              size="large"
              :disabled="busy"
            />
          </div>
          <p v-if="error" class="ui-error" role="alert">{{ error }}</p>
          <el-button
            class="mt-1 min-h-[45px] w-full [&_.el-icon]:ml-3"
            type="primary"
            native-type="submit"
            size="large"
            :loading="busy"
            >登录<el-icon><ArrowRight /></el-icon
          ></el-button>
          <el-button
            v-if="auth.token && !auth.user && error"
            class="mt-3 mr-0 mb-0 ml-0! w-full"
            :disabled="busy"
            @click="restoreSession"
            >重试验证已有登录</el-button
          >
        </form>
        <div
          class="mt-8 border-t border-[#edf0f2] pt-[23px] [&>h3]:mb-2.5 [&>h3]:text-xs [&>h3]:text-[#556b78] [&>p]:text-xs [&>p]:leading-[1.8] [&>p]:text-[#7d8a92]"
        >
          <h3>使用预置账号</h3>
          <p>已创建演示账号时，可点击填入用户名：</p>
          <div
            class="mb-3.5 flex flex-wrap gap-2 [&>.el-button+.el-button]:ml-0"
          >
            <el-button
              size="small"
              :disabled="busy"
              @click="username = 'demo_member'"
              >成员：demo_member</el-button
            ><el-button
              size="small"
              :disabled="busy"
              @click="username = 'demo_reviewer'"
              >审批人：demo_reviewer</el-button
            >
          </div>
          <p class="text-xs">
            密码由创建账号的人设置。需要账号时，请联系管理员。
          </p>
        </div>
      </div>
      <p class="mt-[30px] mb-0 text-[11px] text-[#8f9ca5]">
        DevPilot · AI 项目协作助手
      </p>
    </section>
  </main>
</template>
