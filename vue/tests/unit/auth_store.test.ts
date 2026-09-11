import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import * as authApi from "@/api/auth_api";
import { ApiError } from "@/api/http_client";
import { TOKEN_KEY, useAuthStore } from "@/stores/auth_store";
import type { UserVO } from "@/types/api";

vi.mock("@/api/auth_api", () => ({ login: vi.fn(), getCurrentUser: vi.fn() }));
const user: UserVO = {
  id: "测试用户",
  username: "member",
  role: "member",
  created_at: "2026-09-10T00:00:00Z",
  updated_at: "2026-09-10T00:00:00Z",
};
beforeEach(() => {
  sessionStorage.clear();
  setActivePinia(createPinia());
});

describe("登录状态", () => {
  it("只保存令牌，退出时清理令牌和用户", async () => {
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: "新令牌",
      token_type: "bearer",
      expires_in: 1800,
      user,
    });
    const auth = useAuthStore();
    await auth.signIn({ username: "member", password: "不应保存的密码" });
    expect(auth.isMember).toBe(true);
    expect(sessionStorage.getItem(TOKEN_KEY)).toBe("新令牌");
    expect(sessionStorage.length).toBe(1);
    auth.clearSession();
    expect(auth.user).toBeNull();
    expect(sessionStorage.getItem(TOKEN_KEY)).toBeNull();
  });

  it("刷新后从后端重新确认角色，并合并同时发起的恢复请求", async () => {
    sessionStorage.setItem(TOKEN_KEY, "已有令牌");
    vi.mocked(authApi.getCurrentUser).mockResolvedValue({
      ...user,
      role: "reviewer",
    });
    const auth = useAuthStore();
    await Promise.all([auth.restore(), auth.restore()]);
    expect(authApi.getCurrentUser).toHaveBeenCalledTimes(1);
    expect(auth.homePath).toBe("/reviewer");
  });

  it("过期令牌会被清除", async () => {
    sessionStorage.setItem(TOKEN_KEY, "过期令牌");
    vi.mocked(authApi.getCurrentUser).mockRejectedValue(
      new ApiError("登录失效", 401, "invalid_credentials"),
    );
    const auth = useAuthStore();
    await auth.restore();
    expect(auth.token).toBeNull();
  });

  it("临时网络失败时保留令牌以便重试", async () => {
    sessionStorage.setItem(TOKEN_KEY, "已有令牌");
    vi.mocked(authApi.getCurrentUser).mockRejectedValue(
      new ApiError("网络失败", 0, "network_error"),
    );
    const auth = useAuthStore();
    await expect(auth.restore()).rejects.toMatchObject({
      code: "network_error",
    });
    expect(auth.token).toBe("已有令牌");
    expect(auth.user).toBeNull();
  });

  it("退出后不接纳较早请求返回的用户信息", async () => {
    sessionStorage.setItem(TOKEN_KEY, "已有令牌");
    let resolve!: (user: UserVO) => void;
    vi.mocked(authApi.getCurrentUser).mockReturnValue(
      new Promise((done) => {
        resolve = done;
      }),
    );
    const auth = useAuthStore();
    const restoring = auth.restore();
    auth.clearSession();
    resolve(user);
    await restoring;
    expect(auth.user).toBeNull();
  });
});
