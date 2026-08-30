from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
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

    def test_skips_when_already_succeeded_today(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            health = root / "health.json"
            lock = root / "etl.lock"
            now = datetime.now().astimezone().isoformat(timespec="seconds")
            health.write_text(
                json.dumps({"status": "success", "finished_at": now, "run_id": "prev"}),
                encoding="utf-8",
            )
            called = {"n": 0}

            def runner() -> dict:
                called["n"] += 1
                return {"status": "success", "run_id": "should-not-run"}

            result = run_once(runner=runner, health_path=health, lock_path=lock)
            self.assertEqual(result["status"], "skipped_already_today")
            self.assertEqual(called["n"], 0)
            saved = json.loads(health.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "success")
            self.assertEqual(saved["run_id"], "prev")

    def test_force_ignores_daily_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            health = root / "health.json"
            lock = root / "etl.lock"
            now = datetime.now().astimezone().isoformat(timespec="seconds")
            health.write_text(
                json.dumps({"status": "success", "finished_at": now, "run_id": "prev"}),
                encoding="utf-8",
            )

            result = run_once(
                runner=lambda: {"status": "success", "run_id": "forced", "nivel": "verde"},
                health_path=health,
                lock_path=lock,
                force=True,
            )
            self.assertEqual(result["status"], "success")
            self.assertEqual(result["run_id"], "forced")


if __name__ == "__main__":
    unittest.main()
