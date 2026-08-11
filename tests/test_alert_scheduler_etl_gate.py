from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from sisclima.alerts.scheduler import _etl_health_status, run_once


class AlertSchedulerEtlGateTests(unittest.TestCase):
    def test_missing_health_file_blocks_alert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"
            with patch.dict(
                os.environ,
                {
                    "ALERT_REQUIRE_FRESH_ETL": "true",
                    "ETL_HEALTH_FILE": str(missing),
                },
                clear=False,
            ):
                result = run_once()
            self.assertEqual(result["status"], "etl_indisponivel")
            self.assertEqual(result["etl"]["reason"], "health_file_missing")

    def test_recent_success_allows_alert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            health = Path(tmp) / "health.json"
            health.write_text(
                json.dumps(
                    {
                        "status": "success",
                        "run_id": "run-1",
                        "finished_at": datetime.now().astimezone().isoformat(),
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "ALERT_REQUIRE_FRESH_ETL": "true",
                    "ALERT_MAX_ETL_AGE_HOURS": "12",
                    "ETL_HEALTH_FILE": str(health),
                },
                clear=False,
            ):
                ready, meta = _etl_health_status()
                result = run_once()
            self.assertTrue(ready)
            self.assertEqual(meta["status"], "fresh")
            self.assertEqual(result["status"], "enviado")

    def test_stale_success_blocks_alert(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            health = Path(tmp) / "health.json"
            health.write_text(
                json.dumps(
                    {
                        "status": "success",
                        "run_id": "run-old",
                        "finished_at": (datetime.now().astimezone() - timedelta(hours=13)).isoformat(),
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "ALERT_REQUIRE_FRESH_ETL": "true",
                    "ALERT_MAX_ETL_AGE_HOURS": "12",
                    "ETL_HEALTH_FILE": str(health),
                },
                clear=False,
            ):
                ready, meta = _etl_health_status()
            self.assertFalse(ready)
            self.assertEqual(meta["status"], "stale")


if __name__ == "__main__":
    unittest.main()
