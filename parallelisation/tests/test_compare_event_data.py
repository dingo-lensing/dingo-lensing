"""Unit tests for compare_event_data.py's comparisons (the HDF5 reading runs on the cluster)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "option_a"))

try:
    import numpy as np

    from compare_event_data import compare_arrays, segment_duration, time_shift

    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False


@unittest.skipUnless(HAVE_NUMPY, "needs numpy")
class TestCompareEventData(unittest.TestCase):
    def strain(self, n=4097, seed=1):
        rng = np.random.default_rng(seed)
        return rng.normal(size=n) + 1j * rng.normal(size=n)

    def test_identical_arrays(self):
        a = self.strain()
        result = compare_arrays(a, a.copy(), 0.25)
        self.assertTrue(result["identical"])
        self.assertEqual(result["differing_elements"], 0)
        self.assertNotIn("time_shift", result)

    def test_a_pure_time_shift_is_measured(self):
        a = self.strain()
        frequencies = np.arange(len(a)) * 0.25
        for dt in (2.4e-7, 1 / 4096, -3e-5):
            with self.subTest(dt=dt):
                b = a * np.exp(-2j * np.pi * frequencies * dt)
                shift = compare_arrays(a, b, 0.25)["time_shift"]
                self.assertAlmostEqual(shift["dt"], dt, delta=abs(dt) * 1e-6 + 1e-12)
                self.assertLess(shift["phase_residual_rms"], 1e-6)
                self.assertAlmostEqual(shift["amplitude_ratio_range"][0], 1.0)

    def test_a_different_realisation_is_not_a_time_shift(self):
        a, b = self.strain(seed=1), self.strain(seed=2)
        result = compare_arrays(a, b, 0.25)
        self.assertFalse(result["identical"])
        self.assertGreater(result["time_shift"]["phase_residual_rms"], 0.5)
        self.assertGreater(result["relative_difference"], 0.5)

    def test_segment_duration_from_the_settings_attribute(self):
        settings = "{'time_event': 1126259462.4, 'T': 4.0, 'f_s': 4096.0}"
        self.assertEqual(segment_duration({"@settings": settings}), 4.0)
        self.assertEqual(segment_duration({"@settings": settings.encode()}), 4.0)
        self.assertEqual(segment_duration({"settings/T": 8.0}), 8.0)
        self.assertIsNone(segment_duration({}))
        self.assertIsNone(segment_duration({"@settings": "not a dict"}))

    def test_real_arrays_have_no_time_shift(self):
        a = np.abs(self.strain())
        self.assertIsNone(time_shift(a, a * 1.01, 0.25))
        self.assertEqual(compare_arrays(a, a[:-1], 0.25)["identical"], False)


if __name__ == "__main__":
    unittest.main()
