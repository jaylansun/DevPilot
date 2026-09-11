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
  <div class="app-shell">
    <a class="skip-link" href="#main-content">跳到页面内容</a>
    <aside class="sidebar">
      <RouterLink :to="auth.homePath" class="brand brand-light"
        ><span class="brand-icon"><MagicStick /></span>DevPilot</RouterLink
      >
      <div class="workspace-label">
        <span class="workspace-monogram">D</span>
        <div>个人工作区<span>把想法变成行动</span></div>
      </div>
      <p class="nav-caption">工作空间</p>
      <nav aria-label="主导航">
        <RouterLink
          v-if="auth.isMember"
          to="/projects"
          class="nav-link"
          :class="{ active: route.path.startsWith('/projects') }"
          ><el-icon><FolderOpened /></el-icon>我的项目<el-icon class="nav-arrow"
            ><ArrowRight /></el-icon></RouterLink
        ><RouterLink v-else to="/reviewer" class="nav-link active"
          ><el-icon><CircleCheck /></el-icon>审批工作区</RouterLink
        >
      </nav>
      <div class="sidebar-note">
        <span class="note-line"></span>
        <p>先把目标写下来，<br />下一步就会更清楚。</p>
      </div>
      <div class="profile">
        <div class="avatar">
          {{ auth.user?.username.slice(0, 1).toUpperCase() }}
        </div>
        <div class="profile-info">
          <strong>{{ auth.user?.username }}</strong
          ><span>{{ auth.isMember ? "项目成员" : "审批人" }}</span>
        </div>
        <el-button
          text
          circle
          class="logout-button"
          aria-label="退出登录"
          title="退出登录"
          @click="signOut"
          ><el-icon><SwitchButton /></el-icon
        ></el-button>
      </div>
    </aside>
    <div class="app-main">
      <header class="topbar">
        <div class="breadcrumb">
          <span>工作区</span><span>/</span
          ><strong>{{ route.meta.title }}</strong>
        </div>
        <div class="topbar-user">
          <span class="presence-dot"></span
          >{{ auth.isMember ? "成员工作区" : "审批人工作区" }}
        </div>
      </header>
      <main id="main-content" class="page-content">
        <RouterView :key="route.path" />
      </main>
      <footer class="workspace-footer">
        DevPilot<span>每一个项目，从清晰的目标开始。</span>
      </footer>
    </div>
  </div>
</template>
