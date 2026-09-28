import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "docker_build_retry.sh"
TLS_ERROR = (
    "target api: failed to solve: python:3.12-slim: failed to resolve source metadata "
    "for docker.io/library/python:3.12-slim: failed to do request: "
    'Head "https://registry-1.docker.io/v2/library/python/manifests/3.12-slim": '
    "net/http: TLS handshake timeout"
)


class DockerBuildRetryTests(unittest.TestCase):
    def run_build(self, *, failures=0, message=TLS_ERROR, exit_code=42):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fake_build = root / "fake-build"
            fake_build.write_text(
                "#!/usr/bin/env bash\n"
                "attempt=0\n"
                '[ ! -f "$BUILD_RETRY_STATE" ] || read -r attempt < "$BUILD_RETRY_STATE"\n'
                "attempt=$((attempt + 1))\n"
                'printf "%s\\n" "$attempt" > "$BUILD_RETRY_STATE"\n'
                'if [ "$attempt" -le "$BUILD_RETRY_FAILURES" ]; then\n'
                '    printf "%s\\n" "$BUILD_RETRY_MESSAGE"\n'
                '    exit "$BUILD_RETRY_EXIT"\n'
                "fi\n"
                "echo build-complete\n"
            )
            fake_build.chmod(0o700)
            fake_sleep = root / "sleep"
            fake_sleep.write_text(
                '#!/bin/sh\nprintf "%s\\n" "$1" >> "$BUILD_RETRY_DELAYS"\n'
            )
            fake_sleep.chmod(0o700)
            env = {
                **os.environ,
                "PATH": f"{root}{os.pathsep}{os.environ['PATH']}",
                "TMPDIR": str(root),
                "BUILD_RETRY_STATE": str(root / "attempts"),
                "BUILD_RETRY_FAILURES": str(failures),
                "BUILD_RETRY_MESSAGE": message,
                "BUILD_RETRY_EXIT": str(exit_code),
                "BUILD_RETRY_DELAYS": str(root / "delays"),
            }
            result = subprocess.run(
                ["bash", str(SCRIPT), str(fake_build)],
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            attempts = int((root / "attempts").read_text())
            delays = (
                (root / "delays").read_text().splitlines()
                if (root / "delays").exists()
                else []
            )
            self.assertFalse(list(root.glob("devpilot-docker-build.*")))
            return result, attempts, delays

    def test_success_without_retry(self):
        result, attempts, delays = self.run_build()
        self.assertEqual((result.returncode, attempts, delays), (0, 1, []))
        self.assertIn("build-complete", result.stdout)

    def test_transient_registry_error_recovers(self):
        result, attempts, delays = self.run_build(failures=2)
        self.assertEqual((result.returncode, attempts, delays), (0, 3, ["5", "10"]))
        self.assertIn(TLS_ERROR, result.stdout)
        self.assertIn("build-complete", result.stdout)

    def test_eof_stops_after_three_attempts_with_original_exit_code(self):
        result, attempts, delays = self.run_build(
            failures=99,
            message=TLS_ERROR.replace("net/http: TLS handshake timeout", "EOF"),
        )
        self.assertEqual((result.returncode, attempts, delays), (42, 3, ["5", "10"]))

    def test_token_connection_failure_can_retry(self):
        result, attempts, _ = self.run_build(
            failures=1,
            message="ERROR: failed to fetch anonymous token: connection reset by peer",
        )
        self.assertEqual((result.returncode, attempts), (0, 2))

    def test_gateway_and_temporary_server_failures_can_retry(self):
        for reason in (
            "Bad Gateway",
            "503 Service Unavailable",
            "Gateway Timeout",
            "unexpected status from HEAD request: 500 Internal Server Error",
        ):
            with self.subTest(reason=reason):
                result, attempts, _ = self.run_build(
                    failures=1,
                    message=TLS_ERROR.replace(
                        "net/http: TLS handshake timeout", reason
                    ),
                )
                self.assertEqual((result.returncode, attempts), (0, 2))

    def test_code_auth_tag_and_dependency_failures_are_not_retried(self):
        for message in (
            "ERROR: process npm run build did not complete successfully: exit code 1",
            "FAILED tests/test_workflow.py::test_report",
            "ERROR: failed to resolve source metadata: pull access denied",
            "ERROR: failed to resolve source metadata: manifest unknown",
            "ERROR: failed to fetch anonymous token: 401 Unauthorized",
            "ERROR: failed to resolve source metadata: unexpected status: 429 Too Many Requests",
            "RUN npm ci: TLS handshake timeout",
        ):
            with self.subTest(message=message):
                result, attempts, delays = self.run_build(failures=99, message=message)
                self.assertEqual((result.returncode, attempts, delays), (42, 1, []))

    def test_cancellation_is_not_retried(self):
        result, attempts, delays = self.run_build(failures=99, exit_code=130)
        self.assertEqual((result.returncode, attempts, delays), (130, 1, []))
