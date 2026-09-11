import { computed, ref } from "vue";
import { defineStore } from "pinia";
import * as authApi from "@/api/auth_api";
import { ApiError } from "@/api/http_client";
import type { LoginQO, UserVO } from "@/types/api";

export const TOKEN_KEY = "devpilot.access_token";

function readToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(readToken());
  const user = ref<UserVO | null>(null);
  const isMember = computed(() => user.value?.role === "member");
  const homePath = computed(() => (isMember.value ? "/projects" : "/reviewer"));
  let restoring: Promise<void> | null = null;

  function clearSession() {
    token.value = null;
    user.value = null;
    try {
      sessionStorage.removeItem(TOKEN_KEY);
    } catch {
      /* 内存中的登录态仍会清理。 */
    }
  }

  async function signIn(qo: LoginQO) {
    const result = await authApi.login(qo);
    token.value = result.access_token;
    user.value = result.user;
    // 只在当前标签页保存令牌；刷新时重新向后端确认账号和角色。
    try {
      sessionStorage.setItem(TOKEN_KEY, result.access_token);
    } catch {
      /* 浏览器禁用存储时仅保留本次登录。 */
    }
  }

  async function restore() {
    if (!token.value || user.value) return;
    if (restoring) return restoring;
    const savedToken = token.value;
    restoring = (async () => {
      try {
        const result = await authApi.getCurrentUser(savedToken);
        if (token.value === savedToken) user.value = result;
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          if (token.value === savedToken) clearSession();
          return;
        }
        // 网络暂时失败时保留令牌，允许用户重试验证。
        throw error;
      } finally {
        restoring = null;
      }
    })();
    return restoring;
  }

  return { token, user, isMember, homePath, signIn, restore, clearSession };
});
