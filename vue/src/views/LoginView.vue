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
  <main class="login-shell">
    <section class="login-story" aria-label="DevPilot 简介">
      <a class="brand brand-light" href="/login"
        ><span class="brand-icon"><MagicStick /></span>DevPilot<span
          class="brand-caption"
          >项目协作助手</span
        ></a
      >
      <div class="story-content">
        <p class="eyebrow">从一个想法，开始协作</p>
        <h1>让每一个想法，<br />都有清晰的下一步。</h1>
        <p class="story-description">
          把需求整理到一起，让项目有方向，<br />让每一项工作都有着落。
        </p>
        <div class="story-example" aria-label="项目与任务示例">
          <div class="example-heading">
            <span class="example-dot"></span>餐厅外卖网站<span
              class="example-label"
              >示例</span
            >
          </div>
          <p>让顾客在线点餐，让餐厅轻松接单。</p>
          <div class="example-task">
            <span class="task-check done">✓</span>梳理菜单与点餐流程<span
              >已完成</span
            >
          </div>
          <div class="example-task">
            <span class="task-check active"></span>设计购物车页面<span
              >进行中</span
            >
          </div>
          <div class="example-task">
            <span class="task-check"></span>接入订单支付<span>待办</span>
          </div>
        </div>
      </div>
      <p class="story-footer">想法 · 需求 · 行动</p>
    </section>
    <section class="login-panel">
      <div class="login-form-wrap">
        <p class="eyebrow">欢迎回来</p>
        <h2>登录你的工作区</h2>
        <p class="muted login-subtitle">继续推进你的项目。</p>
        <el-alert
          v-if="route.query.reason === 'expired'"
          title="登录已失效，请重新登录"
          type="warning"
          :closable="false"
          show-icon
        />
        <form class="login-form" @submit.prevent="signIn">
          <div class="form-field">
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
          <div class="form-field">
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
          <p v-if="error" class="inline-error" role="alert">{{ error }}</p>
          <el-button
            class="login-submit"
            type="primary"
            native-type="submit"
            size="large"
            :loading="busy"
            >登录<el-icon><ArrowRight /></el-icon
          ></el-button>
          <el-button
            v-if="auth.token && !auth.user && error"
            class="restore-button"
            :disabled="busy"
            @click="restoreSession"
            >重试验证已有登录</el-button
          >
        </form>
        <div class="demo-hint">
          <h3>使用预置账号</h3>
          <p>已创建演示账号时，可点击填入用户名：</p>
          <div class="demo-actions">
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
          <p class="small">
            密码由创建账号的人设置。需要账号时，请联系管理员。
          </p>
        </div>
      </div>
      <p class="login-footer">DevPilot · AI 项目协作助手</p>
    </section>
  </main>
</template>
