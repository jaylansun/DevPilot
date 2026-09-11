export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
    public readonly requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

let getToken: () => string | null = () => null;
let onUnauthorized: (token: string) => void = () => undefined;

export function configureAuth(
  tokenProvider: () => string | null,
  unauthorizedHandler: (token: string) => void,
) {
  getToken = tokenProvider;
  onUnauthorized = unauthorizedHandler;
}

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  token?: string | null;
};

const messages: Record<number, string> = {
  401: "登录已失效，请重新登录",
  403: "当前账号没有执行此操作的权限",
  404: "请求的内容不存在或已被删除",
  409: "数据发生冲突，请刷新后重试",
  422: "请检查输入内容",
  500: "服务暂时无法处理请求，请稍后重试",
  502: "后端服务暂时不可用，请稍后重试",
  503: "服务正在启动，请稍后重试",
};

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const token = options.token === undefined ? getToken() : options.token;
  const headers = new Headers({ Accept: "application/json" });
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body !== undefined)
    headers.set("Content-Type", "application/json");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20_000);
  try {
    const response = await fetch(`/api/v1${path}`, {
      method: options.method ?? "GET",
      headers,
      credentials: "omit",
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: controller.signal,
    });
    if (response.status === 204) return undefined as T;
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      if (response.status === 401 && token) onUnauthorized(token);
      const error = payload?.error;
      throw new ApiError(
        typeof error?.message === "string"
          ? error.message
          : (messages[response.status] ?? "请求失败，请稍后重试"),
        response.status,
        typeof error?.code === "string" ? error.code : "http_error",
        typeof error?.request_id === "string" ? error.request_id : undefined,
      );
    }
    if (payload === null)
      throw new ApiError(
        "服务返回的数据无法读取，请稍后重试",
        response.status,
        "invalid_response",
      );
    return payload as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError(
      controller.signal.aborted
        ? "请求超时，请检查网络后重试"
        : "无法连接服务，请检查网络后重试",
      0,
      controller.signal.aborted ? "timeout" : "network_error",
    );
  } finally {
    clearTimeout(timeout);
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "操作失败，请重试";
}
