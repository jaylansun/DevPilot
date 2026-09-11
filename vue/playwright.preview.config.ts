import { defineConfig } from "@playwright/test";
import baseConfig from "./playwright.config";

// 用相同的浏览器用例检查生产包，捕获工具类提取和样式层顺序问题。
export default defineConfig({
  ...baseConfig,
  webServer: {
    command: "npm run preview -- --host 127.0.0.1 --port 5174 --strictPort",
    url: "http://127.0.0.1:5174",
    reuseExistingServer: false,
  },
});
