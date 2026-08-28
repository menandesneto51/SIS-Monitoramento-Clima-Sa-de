# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from unittest.mock import patch


class SmtpSslSentinelaTests(unittest.TestCase):
    def test_titan_465_usa_ssl_sem_flag(self) -> None:
        from sisclima.alerts.notifier import _smtp_use_ssl

        with patch("sisclima.alerts.notifier.env", return_value=None):
            self.assertTrue(_smtp_use_ssl("smtp.titan.email", 465))

    def test_587_usa_starttls_sem_flag(self) -> None:
        from sisclima.alerts.notifier import _smtp_use_ssl

        with patch("sisclima.alerts.notifier.env", return_value=None):
            self.assertFalse(_smtp_use_ssl("smtp.gmail.com", 587))

    def test_flag_smtp_ssl_manda(self) -> None:
        from sisclima.alerts.notifier import _smtp_use_ssl

        with patch("sisclima.alerts.notifier.env", return_value="true"):
            self.assertTrue(_smtp_use_ssl("smtp.gmail.com", 587))
        with patch("sisclima.alerts.notifier.env", return_value="false"):
            self.assertFalse(_smtp_use_ssl("smtp.titan.email", 465))
