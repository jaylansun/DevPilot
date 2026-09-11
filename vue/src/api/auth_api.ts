import type { LoginQO, TokenVO, UserVO } from "@/types/api";
import { request } from "./http_client";

export function login(qo: LoginQO) {
  return request<TokenVO>("/auth/token", {
    method: "POST",
    body: qo,
    token: null,
  });
}

export function getCurrentUser(token: string) {
  return request<UserVO>("/me", { token });
}
