<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowRight, Lock, User } from "@element-plus/icons-vue";
import { useAuthStore } from "@/stores/auth_store";
import { errorMessage } from "@/api/http_client";
import { safeRedirect } from "@/router";

import AiPresence from "@/components/AiPresence.vue";
import BrandMark from "@/components/BrandMark.vue";

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
  <main class="grid min-h-dvh grid-cols-[1.15fr_1fr] bg-white max-tablet:grid-cols-1">
    <section class="relative m-4 flex min-w-0 flex-col overflow-hidden rounded-[28px] bg-[linear-gradient(150deg,#f4f6fb_0%,#eef1fa_70%,#e8edf9_100%)] px-[9%] py-10 max-tablet:m-0 max-tablet:rounded-none max-tablet:px-6 max-tablet:py-6" aria-label="DevPilot 简介">
      <a class="inline-flex items-center gap-3 text-[24px] font-semibold tracking-tight" href="/login"><span class="block size-10 text-brand"><BrandMark /></span>DevPilot</a>
      <div class="my-auto py-10 max-tablet:mt-5 max-tablet:py-0">
        <div class="relative mx-auto h-[290px] w-full max-w-[350px] max-tablet:hidden"><AiPresence /></div>
        <h1 class="mt-5 mb-5 text-[clamp(32px,3.7vw,54px)] font-semibold leading-[1.3] tracking-tight max-tablet:my-0 max-tablet:text-[27px]">想法有了，<br class="max-tablet:hidden" />一起把它做出来。</h1>
        <p class="mb-0 max-w-[410px] text-base leading-8 text-muted max-tablet:mt-3 max-tablet:text-sm">从一份项目资料，到一个清晰答案，再到可执行的下一步。让 AI 和你一起推进项目。</p>
      </div>
      <div class="flex items-center gap-4 text-[13px] text-muted max-tablet:hidden"><span>项目资料</span><span class="h-px w-7 bg-muted/30" aria-hidden="true"></span><span>知识问答</span><span class="h-px w-7 bg-muted/30" aria-hidden="true"></span><span>行动方案</span></div>
    </section>
    <section class="flex items-center justify-center px-12 py-14 max-tablet:px-6 max-tablet:py-10">
      <div class="ui-enter w-full max-w-[370px]">
        <h2 class="mb-3 text-[32px] font-semibold tracking-tight">欢迎回来</h2>
        <p class="mb-9 text-[15px] leading-7 text-muted">登录你的工作区，继续上一次的灵感。</p>
        <el-alert v-if="route.query.reason === 'expired'" title="登录已失效，请重新登录" type="warning" :closable="false" show-icon />
        <form class="mt-6" @submit.prevent="signIn">
          <div class="ui-field"><label for="login-username">用户名</label><el-input id="login-username" v-model="username" :prefix-icon="User" placeholder="请输入用户名" autocomplete="username" maxlength="64" size="large" :disabled="busy" /></div>
          <div class="ui-field"><label for="login-password">密码</label><el-input id="login-password" v-model="password" :prefix-icon="Lock" type="password" show-password placeholder="请输入密码" autocomplete="current-password" maxlength="128" size="large" :disabled="busy" /></div>
          <p v-if="error" class="ui-error" role="alert">{{ error }}</p>
          <el-button class="mt-3 min-h-12 w-full [&_.el-icon]:ml-3" type="primary" native-type="submit" size="large" :loading="busy">登录<el-icon><ArrowRight /></el-icon></el-button>
          <el-button v-if="auth.token && !auth.user && error" class="mt-3 ml-0! w-full" :disabled="busy" @click="restoreSession">重试验证已有登录</el-button>
        </form>
        <details class="mt-7 text-[13px] leading-7 text-muted">
          <summary class="ui-interactive min-h-11 rounded-lg py-2 hover:text-ink">使用预置账号</summary>
          <div class="ui-enter rounded-xl bg-canvas p-4">
            <p class="mb-3">已创建演示账号时，可点击填入用户名：</p>
            <div class="mb-3 flex flex-wrap gap-2 [&>.el-button+.el-button]:ml-0">
              <el-button size="small" :disabled="busy" @click="username = 'demo_member'">成员：demo_member</el-button>
              <el-button size="small" :disabled="busy" @click="username = 'demo_reviewer'">审批人：demo_reviewer</el-button>
            </div>
            <p class="mb-0">密码由创建账号的人设置。需要账号时，请联系管理员。</p>
          </div>
        </details>
        <p class="mb-0 mt-12 text-xs leading-6 text-muted">你的项目、知识与思考，都从这里继续。</p>
      </div>
    </section>
  </main>
</template>
