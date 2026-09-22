"""一条命令验证第十三天：隔离数据库/索引、离线模型、真实 HTTP/浏览器和进程重启。"""

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "service"
VUE = ROOT / "vue"
PYTHON = SERVICE / ".venv/bin/python"


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def stop(process):
    if process and process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--integration-only",
        action="store_true",
        help="只运行 PostgreSQL 专项与三阶段真实浏览器验收",
    )
    args = parser.parse_args()
    if not PYTHON.exists() or not (VUE / "node_modules").is_dir():
        parser.error("请先在 service 执行 uv sync --frozen，并在 vue 执行 npm ci")
    run_id = uuid4().hex[:10]
    report_dir = ROOT / "test-results" / f"day13-{run_id}"
    report_dir.mkdir(parents=True)
    database_container = f"devpilot-day13-{run_id}"
    api_port, web_port = free_port(), free_port()
    while web_port == api_port:
        web_port = free_port()
    report = {"status": "running", "checks": [], "models": "offline", "api_restarts": 0}
    api_process = None
    api_log = None
    container_created = False

    def command(name, argv, cwd, env, timeout=300):
        print(f"开始：{name}", flush=True)
        if argv[0] == "npx":
            argv = [*argv, "--output", str(report_dir / name)]
        with (report_dir / f"{name}.log").open("w") as output:
            process = subprocess.Popen(
                argv,
                cwd=cwd,
                env=env,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            try:
                code = process.wait(timeout=timeout)
                if code:
                    raise RuntimeError(f"{name} 失败，退出码 {code}")
            finally:
                stop(process)
        report["checks"].append(name)
        print(f"通过：{name}", flush=True)

    def wait_api():
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if api_process.poll() is not None:
                raise RuntimeError("测试 API 启动失败，请查看 api 日志")
            try:
                with urlopen(
                    f"http://127.0.0.1:{api_port}/api/v1/health", timeout=1
                ) as response:
                    if response.status == 200:
                        return
            except (URLError, TimeoutError):
                pass
            time.sleep(0.2)
        raise RuntimeError("等待测试 API 超时")

    try:
        with ExitStack() as stack:
            temporary = stack.enter_context(
                tempfile.TemporaryDirectory(prefix="devpilot-day13-")
            )
            stack.callback(lambda: api_log.close() if api_log else None)
            stack.callback(lambda: stop(api_process))
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--detach",
                    "--rm",
                    "--name",
                    database_container,
                    "--env",
                    "POSTGRES_PASSWORD=day13-isolated-test",
                    "--env",
                    "POSTGRES_DB=day13_test",
                    "--publish",
                    "127.0.0.1::5432",
                    "--tmpfs",
                    "/var/lib/postgresql/data",
                    "pgvector/pgvector:pg17",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            container_created = True
            port = (
                subprocess.check_output(
                    ["docker", "port", database_container, "5432/tcp"], text=True
                )
                .strip()
                .rsplit(":", 1)[1]
            )
            url = f"postgresql+psycopg://postgres:day13-isolated-test@127.0.0.1:{port}/day13_test"
            env = {
                **os.environ,
                "AI_MODE": "mock",
                "MODEL_NAME": "",
                "LLM_API_KEY": "",
                "LLM_BASE_URL": "",
                "DATABASE_URL": url,
                "TEST_APPROVAL_DATABASE_URL": url,
                "JWT_SECRET": "day13-isolated-test-secret-not-for-deployment",
                "KNOWLEDGE_DATA_DIR": str(Path(temporary) / "knowledge"),
                "RAG_MIN_SCORE": "0.5",
                "LANGSMITH_TRACING": "false",
                "LANGCHAIN_TRACING_V2": "false",
                "PYTHONPATH": str(SERVICE),
                "DEVPILOT_E2E_PORT": str(web_port),
                "DEVPILOT_API_PROXY": f"http://127.0.0.1:{api_port}",
                "DEVPILOT_JOURNEY_STATE": str(Path(temporary) / "journey.json"),
            }
            # 普通回归不能意外指向外部配置的旧验收服务。
            env.pop("DEVPILOT_APPROVAL_API", None)
            env.pop("DEVPILOT_JOURNEY_PHASE", None)
            for _ in range(100):
                if (
                    subprocess.run(
                        [
                            "docker",
                            "exec",
                            database_container,
                            "pg_isready",
                            "-U",
                            "postgres",
                            "-d",
                            "day13_test",
                        ],
                        check=False,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    ).returncode
                    == 0
                ):
                    break
                time.sleep(0.2)
            else:
                raise RuntimeError("等待隔离数据库超时")
            command(
                "migrations",
                [str(PYTHON), "-m", "alembic", "upgrade", "head"],
                SERVICE,
                env,
            )
            backend = [str(PYTHON), "-m", "pytest", "-q"]
            if args.integration_only:
                backend.append("tests/test_approvals_postgres.py")
            command("backend", backend, SERVICE, env)
            if not args.integration_only:
                command("frontend-unit", ["npm", "test"], VUE, env)
            command("frontend-build", ["npm", "run", "build"], VUE, env)
            playwright = [
                "npx",
                "--no-install",
                "playwright",
                "test",
                "--config",
                "playwright.preview.config.ts",
            ]
            if not args.integration_only:
                command(
                    "browser-regression",
                    playwright + ["--grep-invert", "真实 API|重启前|重启后|再次重启"],
                    VUE,
                    env,
                )
            for phase, title in [
                ("prepare", "重启前"),
                ("approve", "重启后"),
                ("verify", "再次重启"),
            ]:
                api_log = (report_dir / f"api-{phase}.log").open("w")
                api_process = subprocess.Popen(
                    [
                        str(PYTHON),
                        "-m",
                        "uvicorn",
                        "day13_app:app",
                        "--app-dir",
                        "tests",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(api_port),
                    ],
                    cwd=SERVICE,
                    env=env,
                    stdout=api_log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                wait_api()
                command(
                    f"journey-{phase}",
                    playwright
                    + [
                        "tests/e2e/full_journey.spec.ts",
                        "--grep",
                        title,
                        "--workers=1",
                    ],
                    VUE,
                    {**env, "DEVPILOT_JOURNEY_PHASE": phase},
                )
                stop(api_process)
                api_process = None
                api_log.close()
                api_log = None
                if phase != "verify":
                    report["api_restarts"] += 1
            report["status"] = "passed"
    except (
        OSError,
        RuntimeError,
        subprocess.SubprocessError,
        KeyboardInterrupt,
    ) as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        print(f"验收未通过：{exc}", file=sys.stderr)
    finally:
        stop(api_process)
        if api_log:
            api_log.close()
        if container_created:
            subprocess.run(
                ["docker", "stop", database_container],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
        (report_dir / "report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        )
        print(f"测试报告：{report_dir}", flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
