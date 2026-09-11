import { createApp } from "vue";
import {
  ElAlert,
  ElButton,
  ElConfigProvider,
  ElDialog,
  ElIcon,
  ElInput,
  ElPagination,
  ElSkeleton,
} from "element-plus";
import { createPinia } from "pinia";
import App from "./App.vue";
import "./assets/tailwind.css";
import { router } from "./router";
import { useAuthStore } from "./stores/auth_store";
import { configureAuth } from "./api/http_client";

const app = createApp(App);
const pinia = createPinia();
app.use(pinia);
const auth = useAuthStore(pinia);
configureAuth(
  () => auth.token,
  (token) => {
    // 旧请求的 401 不能清除之后重新登录获得的令牌。
    if (token !== auth.token) return;
    const hadUser = Boolean(auth.user);
    auth.clearSession();
    if (hadUser && router.currentRoute.value.name !== "login") {
      void router.replace({
        name: "login",
        query: {
          reason: "expired",
          redirect: router.currentRoute.value.fullPath,
        },
      });
    }
  },
);
for (const [name, component] of Object.entries({
  ElAlert,
  ElButton,
  ElConfigProvider,
  ElDialog,
  ElIcon,
  ElInput,
  ElPagination,
  ElSkeleton,
})) {
  app.component(name, component);
}
app.use(router).mount("#app");
