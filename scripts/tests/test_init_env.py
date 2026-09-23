import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "init_env", Path(__file__).resolve().parents[1] / "init_env.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class EnvironmentTests(unittest.TestCase):
    def test_random_config_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = (
                Path(directory) / name for name in (".env.one", ".env.two")
            )
            for path in (first, second):
                module.initialize(path, web_port=5185, api_port=8014, db_port=5434)
            raw = first.read_text()
            values = dict(
                line.split("=", 1)
                for line in raw.splitlines()
                if line and not line.startswith("#")
            )
            self.assertIn(values["POSTGRES_PASSWORD"], values["DATABASE_URL"])
            self.assertEqual(values["AI_MODE"], "mock")
            self.assertEqual(values["FRONTEND_ORIGINS"], "http://localhost:5185")
            self.assertNotEqual(raw, second.read_text())
            self.assertEqual(first.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(FileExistsError):
                module.initialize(first)
            self.assertEqual(first.read_text(), raw)

    def test_invalid_ports_do_not_create_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            for web_port in (0, 70000, 8000):
                with self.assertRaises(ValueError):
                    module.initialize(path, web_port=web_port)
            self.assertFalse(path.exists())
