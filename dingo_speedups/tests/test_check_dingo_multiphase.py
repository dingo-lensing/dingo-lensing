"""Unit tests for lal/check_dingo_multiphase.py: its helpers, and that it refuses a LAL other
than build_lal.sh's and a tree the guard refuses, before any DINGO. The check itself runs in
the image on the cluster (lal/run_check_dingo_multiphase.sh). Needs numpy, as the script does."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import SPEEDUPS, load_module, make_tree, run_script, write  # noqa: E402

HAVE_NUMPY = importlib.util.find_spec("numpy") is not None
SCRIPT = SPEEDUPS / "lal" / "check_dingo_multiphase.py"
check = load_module("check_dingo_multiphase_under_test", SCRIPT) if HAVE_NUMPY else None


@unittest.skipUnless(HAVE_NUMPY, "needs numpy")
class TestHelpers(unittest.TestCase):
    def test_largest_difference_is_against_the_largest_reference(self):
        references = [[1.0, -4.0], [0.5, 0.0]]
        arrays = [[1.0, -4.0], [0.5, 0.02]]
        self.assertAlmostEqual(check.largest_difference(arrays, references), 0.005, places=15)
        self.assertEqual(check.largest_difference(references, references), 0.0)

    def test_summarise(self):
        self.assertEqual(check.summarise([3.0, 1.0, 2.0]), {"n": 3, "median": 2.0, "max": 3.0, "min": 1.0})
        self.assertEqual(check.summarise([]), {"n": 0})


@unittest.skipUnless(HAVE_NUMPY, "needs numpy")
class TestRefusals(unittest.TestCase):
    def run_check(self, base: Path, with_function: bool, commit: str):
        site = base / "site"
        write(site / "lal" / "__init__.py", "__version__ = '0'\n")
        body = "__version__ = '0'\n" + ("def SimInspiralFDMultiPhase(*args):\n    pass\n" if with_function else "")
        write(site / "lalsimulation" / "__init__.py", body)
        tree = make_tree(base / "src")
        args = ["--lal-site", str(site), "--tree", str(tree), "--commit", commit, "--output", str(base / "r.json")]
        args += ["--proposal", "p.hdf5", "--event-data", "e.hdf5"]
        return run_script(SCRIPT, args, site=True)

    def test_a_lalsimulation_without_the_function_exits_2(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_check(Path(directory), with_function=False, commit="fedcba9876543210")
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("LAL FAILED", result.stderr)

    def test_then_the_guard_still_refuses_a_wrong_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_check(Path(directory), with_function=True, commit="fedcba9876543210")
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("GUARD FAILED", result.stderr)
            self.assertFalse((Path(directory) / "r.json").exists())


if __name__ == "__main__":
    unittest.main()
