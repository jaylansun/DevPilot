import { spawnSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import openapiTS, { astToString } from "openapi-typescript";

// 从本地后端导出接口定义，不依赖正在运行的服务，也不会导出环境变量。
const serviceDirectory = fileURLToPath(
  new URL("../../service/", import.meta.url),
);
const result = spawnSync(
  "uv",
  [
    "run",
    "--locked",
    "--directory",
    serviceDirectory,
    "python",
    "-c",
    "import json; from app.main import app; print(json.dumps(app.openapi(), ensure_ascii=False))",
  ],
  { encoding: "utf8", env: { ...process.env, PYTHONUTF8: "1" } },
);
if (result.error || result.status !== 0) {
  console.error("导出接口定义失败，请确认已安装 uv 并同步后端依赖。");
  console.error(result.error?.message ?? result.stderr);
  process.exit(1);
}
const schema = JSON.parse(result.stdout);
const source = astToString(await openapiTS(schema)).replace(
  /\/\*\*[\s\S]*?\*\//g,
  "",
);
const target = new URL("../src/types/api.generated.ts", import.meta.url);
await mkdir(new URL("../src/types/", import.meta.url), { recursive: true });
await writeFile(
  target,
  "// 由 npm run generate:api 自动生成，请勿手工修改。\n" + source,
);
console.log("已根据 FastAPI 接口生成 TypeScript 类型。");
