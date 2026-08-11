from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sisclima.etl_scheduler import run_once


class EtlSchedulerTests(unittest.TestCase):
    def test_success_writes_health_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            health = root / "health.json"
            lock = root / "etl.lock"

            result = run_once(
                runner=lambda: {
                    "status": "success",
                    "run_id": "run-123",
                    "nivel": "laranja",
                },
                health_path=health,
                lock_path=lock,
            )

            saved = json.loads(health.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "success")
            self.assertEqual(saved["status"], "success")
            self.assertEqual(saved["run_id"], "run-123")
            self.assertIn("finished_at", saved)

    def test_failure_writes_error_health_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            health = root / "health.json"
            lock = root / "etl.lock"

            def fail() -> dict:
                raise RuntimeError("fonte indisponível")

            with self.assertRaisesRegex(RuntimeError, "fonte indisponível"):
                run_once(runner=fail, health_path=health, lock_path=lock)

            saved = json.loads(health.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "error")
            self.assertIn("fonte indisponível", saved["message"])


if __name__ == "__main__":
    unittest.main()
