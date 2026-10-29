"""Unit tests for lal/check_multiphase.py's helpers, and for what lal/xphm_multiphase.patch may
change in LALSimulation. The check itself runs in the build environment on the cluster
(lal/run_multiphase_check.sh). The helpers need numpy, as check_multiphase.py does; the patch
tests are standard library only."""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

try:
    import numpy as np
except ImportError:  # the helpers' tests are skipped without it
    np = None

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import SPEEDUPS, load_module  # noqa: E402

HAVE_NUMPY = np is not None
CHECK = SPEEDUPS / "lal" / "check_multiphase.py"
check = load_module("check_multiphase_under_test", CHECK) if HAVE_NUMPY else None
PATCH = SPEEDUPS / "lal" / "xphm_multiphase.patch"


@unittest.skipUnless(HAVE_NUMPY, "needs numpy")
class TestHelpers(unittest.TestCase):
    def test_dft_phases_are_dingos(self):
        phases = check.dft_phases()
        self.assertEqual(len(phases), 9)
        self.assertEqual(phases[0], 0.0)
        self.assertAlmostEqual(phases[1], 2 * math.pi / 9, places=15)
        self.assertLess(phases[-1], 2 * math.pi)

    def test_verdict(self):
        self.assertTrue(check.verdict("shared", 1e-14, 1e-10))
        self.assertFalse(check.verdict("shared", 0.0, 1e-10))  # exact: it fell back
        self.assertFalse(check.verdict("shared", 1e-9, 1e-10))
        self.assertTrue(check.verdict("fallback", 0.0, 1e-10))
        self.assertFalse(check.verdict("fallback", 1e-16, 1e-10))
        self.assertTrue(check.verdict("either", 0.0, 1e-10))
        self.assertTrue(check.verdict("either", 1e-12, 1e-10))
        self.assertFalse(check.verdict("either", math.inf, 1e-10))

    def test_summarise_drops_nans(self):
        expected = {"n": 3, "median": 2.0, "max": 3.0, "min": 1.0}
        self.assertEqual(check.summarise([3.0, math.nan, 1.0, 2.0]), expected)
        self.assertEqual(check.summarise([]), {"n": 0})


@unittest.skipUnless(HAVE_NUMPY, "needs numpy")
class TestNumerics(unittest.TestCase):
    def test_relative_difference_is_the_worst_row_against_its_peak(self):
        reference = np.array([[1.0, 2.0j, -4.0], [10.0, 0.0, 0.0]])
        other = reference.copy()
        other[0, 1] += 0.04
        other[1, 0] += 0.01
        self.assertAlmostEqual(check.relative_difference(reference, other), 0.01, places=15)
        self.assertEqual(check.relative_difference(reference, reference), 0.0)

    def test_relative_difference_flags_shapes_nans_and_zero_references(self):
        a = np.ones((2, 3), dtype=complex)
        self.assertEqual(check.relative_difference(a, a[:, :2]), math.inf)
        b = a.copy()
        b[1, 2] = np.nan
        self.assertEqual(check.relative_difference(a, b), math.inf)
        self.assertEqual(check.relative_difference(np.zeros(3), np.array([0.0, 1e-30, 0.0])), math.inf)
        self.assertEqual(check.relative_difference(np.zeros(3), np.zeros(3)), 0.0)

    def test_mismatch(self):
        weights = np.array([1.0, 2.0, 0.5])
        a = np.array([1 + 1j, 2 - 1j, 0.5j])
        orthogonal = (np.array([1.0, 0, 0]), np.array([0, 1.0, 0]))
        self.assertAlmostEqual(check.mismatch(a, a, weights), 0.0, places=15)
        self.assertAlmostEqual(check.mismatch(a, 3.0 * a, weights), 0.0, places=15)
        self.assertAlmostEqual(check.mismatch(*orthogonal, weights), 1.0, places=15)
        self.assertTrue(math.isnan(check.mismatch(np.zeros(3), a, weights)))


class TestPatch(unittest.TestCase):
    def setUp(self):
        self.lines = PATCH.read_text(encoding="utf-8").splitlines()

    def test_only_adds_code_to_the_four_files(self):
        removed = [line for line in self.lines if line.startswith("-") and not line.startswith("---")]
        self.assertEqual(removed, [])
        files = [line.split(" b/")[-1] for line in self.lines if line.startswith("diff --git")]
        expected = [
            "lalsimulation/lib/LALSimIMR.h",
            "lalsimulation/lib/LALSimIMRPhenomXPHM.c",
            "lalsimulation/lib/LALSimInspiral.c",
            "lalsimulation/lib/LALSimInspiral.h"
        ]
        self.assertEqual(files, expected)

    def test_declares_the_functions_and_keeps_lals_real_steps_by_default(self):
        added = [line[1:] for line in self.lines if line.startswith("+") and not line.startswith("+++")]
        self.assertIn("int XLALSimIMRPhenomXPHMMultiPhase(", added)
        self.assertTrue(any(line.startswith("int XLALSimInspiralFDMultiPhase(") for line in added))
        # IMRPhenomXPHM_hplushcross keeps only the real parts of the steps; the default path must too.
        self.assertIn("      REAL8 Omega_alpha, Omega_epsilon, Omega_betah, Qalpha, Qepsilon, Qbetah;", added)
        self.assertIn("            cexp_i_alpha[fine_count]   = Qalpha*cexp_i_alpha[fine_count-1];", added)

    def test_has_lf_line_endings(self):
        self.assertNotIn(b"\r", PATCH.read_bytes())


if __name__ == "__main__":
    unittest.main()
