"""Unit tests for compat_check.py's helpers; the checks themselves need DINGO and
run on the cluster (run_compat_check.sh). Standard library only."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import SPEEDUPS, load_module  # noqa: E402

compat_check = load_module("compat_check_under_test", SPEEDUPS / "compat_check.py")


class TestTimed(unittest.TestCase):
    def test_records_success_and_returns_the_value(self):
        checks = {}
        self.assertEqual(compat_check.timed("one", checks, lambda: 42), 42)
        self.assertTrue(checks["one"]["ok"])
        self.assertGreaterEqual(checks["one"]["seconds"], 0)
        self.assertNotIn("error", checks["one"])

    def test_records_a_failure_with_its_traceback_and_returns_none(self):
        checks = {}

        def broken():
            raise ValueError("no such model")

        self.assertIsNone(compat_check.timed("two", checks, broken))
        self.assertFalse(checks["two"]["ok"])
        self.assertIn("ValueError: no such model", checks["two"]["error"])


class TestExitCode(unittest.TestCase):
    def test_zero_only_when_every_check_passed(self):
        self.assertEqual(compat_check.exit_code({"a": {"ok": True}, "b": {"ok": True}}), 0)
        self.assertEqual(compat_check.exit_code({"a": {"ok": True}, "b": {"ok": False}}), 1)

    def test_no_checks_at_all_is_a_failure(self):
        self.assertEqual(compat_check.exit_code({}), 1)


if __name__ == "__main__":
    unittest.main()
