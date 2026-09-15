<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowRight, MagicStick, Lock, User } from "@element-plus/icons-vue";
import { useAuthStore } from "@/stores/auth_store";
import { errorMessage } from "@/api/http_client";
import { safeRedirect } from "@/router";

import AiPresence from "@/components/AiPresence.vue";

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
  <main class="grid min-h-dvh grid-cols-[1.1fr_1fr] bg-canvas max-tablet:grid-cols-1">
    <section class="relative flex min-w-0 flex-col overflow-hidden border-r border-line/60 px-[10%] py-10 max-tablet:border-r-0 max-tablet:border-b max-tablet:px-6 max-tablet:py-6" aria-label="DevPilot 简介">
      <a class="inline-flex items-center gap-3 text-2xl font-semibold tracking-tight" href="/login">
        <span class="grid size-10 place-items-center rounded-xl border border-brand/40 bg-brand/10 text-xl text-brand"><MagicStick aria-hidden="true" /></span>DevPilot
      </a>
      <div class="my-auto max-tablet:mt-6">
        <div class="mx-auto h-[360px] w-full max-w-[410px] max-tablet:hidden"><AiPresence /></div>
        <h1 class="mt-4 mb-5 text-[clamp(32px,3.4vw,52px)] font-semibold leading-[1.3] tracking-tight max-tablet:my-0 max-tablet:text-2xl">从想法，<br class="max-tablet:hidden" />到清晰的下一步。</h1>
        <p class="mb-0 max-w-[380px] text-base leading-8 text-muted max-tablet:mt-3 max-tablet:text-sm">让项目资料成为依据，让 AI 帮你理清问题、拆解目标，回到真正重要的工作。</p>
      </div>
      <div class="mt-7 flex flex-wrap gap-6 border-t border-line/60 pt-5 text-xs text-muted max-tablet:hidden"><span>项目知识库</span><span>有来源的问答</span><span>可审阅的任务草案</span></div>
    </section>
    <section class="flex items-center justify-center bg-surface/50 px-10 py-12 max-tablet:px-6 max-tablet:py-8">
      <div class="w-full max-w-[380px]">
        <h2 class="mb-3 text-[28px] font-semibold tracking-tight">登录你的工作区</h2>
        <p class="ui-muted mb-8">欢迎回来，继续推进你的项目。</p>
        <el-alert v-if="route.query.reason === 'expired'" title="登录已失效，请重新登录" type="warning" :closable="false" show-icon />
        <form class="mt-6" @submit.prevent="signIn">
          <div class="ui-field"><label for="login-username">用户名</label><el-input id="login-username" v-model="username" :prefix-icon="User" placeholder="请输入用户名" autocomplete="username" maxlength="64" size="large" :disabled="busy" /></div>
          <div class="ui-field"><label for="login-password">密码</label><el-input id="login-password" v-model="password" :prefix-icon="Lock" type="password" show-password placeholder="请输入密码" autocomplete="current-password" maxlength="128" size="large" :disabled="busy" /></div>
          <p v-if="error" class="ui-error" role="alert">{{ error }}</p>
          <el-button class="mt-1 min-h-12 w-full [&_.el-icon]:ml-3" type="primary" native-type="submit" size="large" :loading="busy">登录<el-icon><ArrowRight /></el-icon></el-button>
          <el-button v-if="auth.token && !auth.user && error" class="mt-3 ml-0! w-full" :disabled="busy" @click="restoreSession">重试验证已有登录</el-button>
        </form>
        <div class="mt-8 border-t border-line/70 pt-6 text-xs leading-6 text-muted">
          <h3 class="mb-2 text-sm font-medium text-ink">使用预置账号</h3>
          <p>已创建演示账号时，可点击填入用户名：</p>
          <div class="mb-4 flex flex-wrap gap-2 [&>.el-button+.el-button]:ml-0">
            <el-button size="small" :disabled="busy" @click="username = 'demo_member'">成员：demo_member</el-button>
            <el-button size="small" :disabled="busy" @click="username = 'demo_reviewer'">审批人：demo_reviewer</el-button>
          </div>
          <p class="mb-0">密码由创建账号的人设置。需要账号时，请联系管理员。</p>
        </div>
      </div>
    </section>
  </main>
</template>
