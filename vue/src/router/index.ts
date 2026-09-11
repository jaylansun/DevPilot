import { createRouter, createWebHistory } from "vue-router";
import { useAuthStore } from "@/stores/auth_store";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("@/views/LoginView.vue"),
      meta: { title: "登录" },
    },
    {
      path: "/",
      component: () => import("@/layouts/AppLayout.vue"),
      meta: { requiresAuth: true },
      children: [
        { path: "", redirect: "/projects" },
        {
          path: "projects",
          name: "projects",
          component: () => import("@/views/ProjectsView.vue"),
          meta: { title: "我的项目", role: "member" },
        },
        {
          path: "projects/:id",
          name: "project",
          component: () => import("@/views/ProjectDetailView.vue"),
          meta: { title: "项目概览", role: "member" },
        },
        {
          path: "reviewer",
          name: "reviewer",
          component: () => import("@/views/ReviewerView.vue"),
          meta: { title: "审批工作区", role: "reviewer" },
        },
      ],
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
  scrollBehavior: () => ({ top: 0 }),
});

router.beforeEach(async (to) => {
  const auth = useAuthStore();
  if (to.name === "login") return auth.user ? auth.homePath : true;
  try {
    await auth.restore();
  } catch {
    return {
      name: "login",
      query: { redirect: to.fullPath, reason: "connection" },
    };
  }
  if (!auth.user) return { name: "login", query: { redirect: to.fullPath } };
  if (to.meta.role && to.meta.role !== auth.user.role) return auth.homePath;
});

router.afterEach((to) => {
  document.title = `${to.meta.title ?? "工作区"} · DevPilot`;
});

export function safeRedirect(value: unknown, fallback: string) {
  if (
    typeof value !== "string" ||
    !/^\/projects(?:\/[a-zA-Z0-9-]+)?(?:\?.*)?$/.test(value)
  )
    return fallback;
  return value;
}
