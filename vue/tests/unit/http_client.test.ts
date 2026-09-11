import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, configureAuth, request } from "@/api/http_client";

const fetchMock = vi.fn();
const expired = vi.fn();
beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  configureAuth(() => "test-token", expired);
});
afterEach(() => vi.unstubAllGlobals());

describe("统一请求客户端", () => {
  it("登录请求不携带旧令牌", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ access_token: "新令牌" })),
    );
    await request("/auth/token", {
      method: "POST",
      body: { username: "member", password: "测试密码" },
      token: null,
    });
    const [url, options] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/v1/auth/token");
    expect(options.headers.has("Authorization")).toBe(false);
    expect(options.credentials).toBe("omit");
  });

  it("携带令牌且正确处理删除成功的空响应", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(
      request("/projects/id", { method: "DELETE" }),
    ).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[0]![1].headers.get("Authorization")).toBe(
      "Bearer test-token",
    );
  });

  it("保留后端的中文错误与请求编号", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          error: {
            code: "project_name_exists",
            message: "当前用户已经拥有同名项目",
            request_id: "请求编号",
          },
        }),
        { status: 409 },
      ),
    );
    await expect(request("/projects")).rejects.toMatchObject({
      status: 409,
      message: "当前用户已经拥有同名项目",
      requestId: "请求编号",
    });
  });

  it("令牌失效时将请求所用令牌交给清理逻辑", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 401 }));
    await expect(request("/me")).rejects.toBeInstanceOf(ApiError);
    expect(expired).toHaveBeenCalledWith("test-token");
  });

  it("网关返回网页错误时显示中文提示", async () => {
    fetchMock.mockResolvedValue(
      new Response("<html>Bad Gateway</html>", { status: 502 }),
    );
    await expect(request("/projects")).rejects.toMatchObject({
      message: "后端服务暂时不可用，请稍后重试",
    });
  });

  it("网络失败时显示可操作的中文提示", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(request("/projects")).rejects.toMatchObject({
      code: "network_error",
      message: "无法连接服务，请检查网络后重试",
    });
  });
});
