"""Unit tests for bench/xphm_profile.py's helpers and its guard. The profile itself
runs in the image on the cluster (bench/run_xphm_profile.sh). Standard library only."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import SPEEDUPS, load_module, make_tree, run_script  # noqa: E402

SCRIPT = SPEEDUPS / "bench" / "xphm_profile.py"
profile = load_module("xphm_profile_under_test", SCRIPT)


class TestHelpers(unittest.TestCase):
    def test_summary_is_in_milliseconds(self):
        self.assertEqual(profile.summary_ms([0.001, 0.003, 0.002]), {"mean_ms": 2.0, "median_ms": 2.0, "min_ms": 1.0, "n": 3})

    def test_timed_returns_the_seconds_and_the_value(self):
        seconds, value = profile.timed(lambda x, y=0: x + y, 2, y=3)
        self.assertEqual(value, 5)
        self.assertGreaterEqual(seconds, 0)

    def test_positions_follow_siminspiralfd(self):
        # m1, m2, S1x, S1y, S1z, S2x, S2y, S2z, distance, inclination, phiRef, ..., f_ref, LALDict, approximant
        self.assertEqual((profile.LAL_DICT, profile.APPROXIMANT), (18, 19))
        self.assertEqual(profile.IN_PLANE_SPINS, (2, 3, 5, 6))


class TestGuard(unittest.TestCase):
    def test_a_refused_commit_exits_2_before_any_dingo_or_lal(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            tree = make_tree(base / "src")
            args = [
                "--tree", str(tree),
                "--commit", "fedcba9876543210",
                "--proposal", "p.hdf5",
                "--event-data", "e.hdf5",
                "--output", str(base / "profile.json"),
            ]
            result = run_script(SCRIPT, args)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("GUARD FAILED", result.stderr)
            self.assertFalse((base / "profile.json").exists())


if __name__ == "__main__":
    unittest.main()
