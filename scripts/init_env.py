"""生成一份带随机开发密钥的配置；绝不覆盖已有文件或输出密钥。"""

import argparse
import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def initialize(output: Path, *, web_port=5173, api_port=8000, db_port=5432):
    ports = (web_port, api_port, db_port)
    if any(not 1 <= port <= 65535 for port in ports) or len(set(ports)) != 3:
        raise ValueError("三个端口必须互不相同，且在 1～65535 之间")
    password = secrets.token_urlsafe(24)
    values = {
        "POSTGRES_PASSWORD": password,
        "DATABASE_URL": f"postgresql+psycopg://devpilot:{password}@db:5432/devpilot",
        "JWT_SECRET": secrets.token_urlsafe(48),
        "FRONTEND_ORIGINS": f"http://localhost:{web_port}",
        "DEVPILOT_WEB_PORT": str(web_port),
        "DEVPILOT_API_PORT": str(api_port),
        "DEVPILOT_DB_PORT": str(db_port),
    }
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    content = (
        "\n".join(
            f"{line.split('=', 1)[0]}={values[line.split('=', 1)[0]]}"
            if "=" in line and line.split("=", 1)[0] in values
            else line
            for line in lines
        )
        + "\n"
    )
    # O_EXCL 同时避免普通重复执行与两个初始化进程意外覆盖配置。
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".env")
    parser.add_argument("--web-port", type=int, default=5173)
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--db-port", type=int, default=5432)
    args = parser.parse_args()
    try:
        initialize(
            args.output,
            web_port=args.web_port,
            api_port=args.api_port,
            db_port=args.db_port,
        )
    except (OSError, ValueError) as exc:
        parser.exit(1, f"未生成配置：{exc}\n")
    print(f"已生成 {args.output}，默认为 mock；真实模型配置请在文件中自行填写。")


if __name__ == "__main__":
    main()
