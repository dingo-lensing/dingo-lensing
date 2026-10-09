"""Unit tests for the DINGO-Lensing fixes that make one config safe for several events.

The code lives in the dingo-lensing repo (branch kailib-parallelisation):
dingo_lensing/pipe/multi_event.py and LensedDataGenerationInput in
dingo_lensing/pipe/data_generation.py. multi_event.py is standard library only and
is loaded straight from the repo checkout next to this one, so its tests run
anywhere; the tests that need DINGO run where it is installed (dingo_env, the
image) and are skipped elsewhere.
"""
from __future__ import annotations

import importlib.util
import inspect
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

SYNC_ROOT = Path(__file__).resolve().parents[2]
# The dingo-lensing checkout sits next to this one: C:\Users\Kaili\dingo-lensing
# here, ~/dingo-lensing on the cluster.
REPO = SYNC_ROOT.parent / "dingo-lensing"
MULTI_EVENT = REPO / "dingo_lensing" / "pipe" / "multi_event.py"


def load_multi_event():
    """Load multi_event.py by path, without writing bytecode into the checkout."""
    spec = importlib.util.spec_from_file_location("lensing_multi_event", MULTI_EVENT)
    module = importlib.util.module_from_spec(spec)
    previous, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module


try:
    from dingo.pipe.data_generation import DataGenerationInput

    from dingo_lensing.pipe import data_generation as lensing_generation

    HAVE_DINGO = True
except ImportError:
    HAVE_DINGO = False

needs_dingo = unittest.skipUnless(HAVE_DINGO, "needs DINGO and DINGO-Lensing (run on the cluster)")
needs_repo = unittest.skipUnless(MULTI_EVENT.is_file(), f"needs the dingo-lensing checkout at {REPO}")


@needs_repo
class TestFrameSpans(unittest.TestCase):
    def setUp(self):
        self.frames = load_multi_event()

    def test_reads_the_span_from_a_standard_name(self):
        span = self.frames.frame_span("gwosc/H-H1_LOSC_4_V1-1126256640-4096.gwf")
        self.assertEqual(span, (1126256640.0, 1126260736.0))
        self.assertEqual(self.frames.frame_span("L-L1_GWOSC_4KHZ_R1-1128676853-4096.gwf"), (1128676853.0, 1128680949.0))
        self.assertEqual(self.frames.frame_span("V-V1_X-1000.5-2.5.gwf"), (1000.5, 1003.0))

    def test_non_standard_names_have_no_span(self):
        for name in ("gwf_files/H1.gwf", "H-H1-1126256640.gwf", "H-H1_X-1126256640-4096.hdf5", "H1-1-2.gwf"):
            with self.subTest(name=name):
                self.assertIsNone(self.frames.frame_span(name))

    def test_frames_overlapping_keeps_only_files_that_overlap(self):
        gw150914 = "gwosc/H-H1_LOSC_4_V1-1126256640-4096.gwf"
        gw151012 = "gwosc/H-H1_LOSC_4_V1-1128677376-4096.gwf"
        frames = [gw150914, gw151012]
        # GW150914's PSD stretch and segment, and GW151012's.
        self.assertEqual(self.frames.frames_overlapping(frames, 1126258948.4, 1126259464.4), [gw150914])
        self.assertEqual(self.frames.frames_overlapping(frames, 1128678386.4, 1128678902.4), [gw151012])
        self.assertEqual(self.frames.frames_overlapping(frames, 1000.0, 2000.0), [])

    def test_overlap_at_the_edges(self):
        frames = ["H-H1_X-100-100.gwf", "H-H1_X-200-100.gwf", "H-H1_X-300-100.gwf"]
        # A span ends where the next begins: [100, 200) and [200, 300).
        self.assertEqual(self.frames.frames_overlapping(frames, 150, 200), [frames[0]])
        self.assertEqual(self.frames.frames_overlapping(frames, 199.5, 200.5), frames[:2])
        self.assertEqual(self.frames.frames_overlapping(frames, 200, 400), frames[1:])

    def test_any_non_standard_name_keeps_every_file(self):
        frames = ["gwf_files/H1.gwf", "H-H1_X-100-100.gwf"]
        self.assertEqual(self.frames.frames_overlapping(frames, 5000, 6000), frames)

    def test_psd_file_names_follow_the_job_label(self):
        self.assertEqual(
            self.frames.psd_file_name("T3c_data1_1128678900-4_generation", "H1"),
            "T3c_data1_1128678900-4_generation_H1_psd.txt",
        )


@needs_dingo
class TestLensedDataGeneration(unittest.TestCase):
    def test_dingo_lensing_comes_from_the_repo_checkout(self):
        # Not from the old copy at the root of the sync branch.
        self.assertTrue(
            Path(lensing_generation.__file__).resolve().is_relative_to(REPO.resolve()),
            lensing_generation.__file__,
        )

    def test_save_hdf5_is_dingos_apart_from_the_psd_file_name(self):
        ours = textwrap.dedent(inspect.getsource(lensing_generation.LensedDataGenerationInput.save_hdf5))
        dingos = textwrap.dedent(inspect.getsource(DataGenerationInput.save_hdf5))

        def body(source):
            # Drop the docstring and compare the code.
            code = source.split('"""')[2]
            return code.splitlines()

        ours_lines, dingos_lines = body(ours), body(dingos)
        self.assertEqual(len(ours_lines), len(dingos_lines), "save_hdf5 changed in DINGO: update the copy")
        changed = [(o, d) for o, d in zip(ours_lines, dingos_lines) if o != d]
        self.assertEqual(len(changed), 1, f"Only the PSD file name may differ from DINGO's: {changed}")
        ours_line, dingos_line = changed[0]
        self.assertIn("psd_file_name(self.label, ifo.name)", ours_line)
        self.assertIn('f"{ifo.name}_psd.txt"', dingos_line)

    def generation(self, data_dict):
        generation = lensing_generation.LensedDataGenerationInput.__new__(lensing_generation.LensedDataGenerationInput)
        generation._data_dict = data_dict
        return generation

    def read(self, generation, start, end):
        seen = []

        def fake_read(instance, det, channel, start_time, end_time, dtype="float64"):
            seen.append(instance.data_dict[det])
            return "data"

        with mock.patch.object(DataGenerationInput, "_gwpy_read", fake_read):
            result = generation._gwpy_read("H1", "H1:LOSC-STRAIN", start, end)
        return result, seen

    def test_reads_only_the_overlapping_frames_and_restores_the_list(self):
        frames = ["gwosc/H-H1_LOSC_4_V1-1126256640-4096.gwf", "gwosc/H-H1_LOSC_4_V1-1128677376-4096.gwf"]
        generation = self.generation({"H1": list(frames)})
        result, seen = self.read(generation, 1128678386.4, 1128678902.4)
        self.assertEqual(result, "data")
        self.assertEqual(seen, [[frames[1]]])
        self.assertEqual(generation.data_dict["H1"], frames)

    def test_expands_a_glob_before_choosing(self):
        with tempfile.TemporaryDirectory() as directory:
            names = ["H-H1_X-100-100.gwf", "H-H1_X-5000-100.gwf"]
            for name in names:
                (Path(directory) / name).write_text("")
            pattern = str(Path(directory) / "H-H1_*.gwf")
            generation = self.generation({"H1": pattern})
            _, seen = self.read(generation, 5010, 5020)
            self.assertEqual(seen, [[str(Path(directory) / names[1])]])
            self.assertEqual(generation.data_dict["H1"], pattern)

    def test_a_single_frame_file_is_left_to_bilby_pipe(self):
        generation = self.generation({"H1": "gwf_files/H1.gwf"})
        _, seen = self.read(generation, 0, 10)
        self.assertEqual(seen, ["gwf_files/H1.gwf"])

    def test_no_overlapping_frame_is_a_clear_error(self):
        generation = self.generation({"H1": ["H-H1_X-100-100.gwf", "H-H1_X-200-100.gwf"]})
        with self.assertRaisesRegex(ValueError, "None of the H1 frame files"):
            self.read(generation, 5000, 6000)

    def test_restores_the_list_when_reading_fails(self):
        frames = ["H-H1_X-100-100.gwf", "H-H1_X-200-100.gwf"]
        generation = self.generation({"H1": list(frames)})

        def failing(instance, *args, **kwargs):
            raise RuntimeError("read failed")

        with mock.patch.object(DataGenerationInput, "_gwpy_read", failing):
            with self.assertRaises(RuntimeError):
                generation._gwpy_read("H1", "H1:X", 150, 160)
        self.assertEqual(generation.data_dict["H1"], frames)


if __name__ == "__main__":
    unittest.main()
