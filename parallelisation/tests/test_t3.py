"""Unit tests for T3 (option A with two different events) and its helpers.

Standard library only.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

OPTION_A = Path(__file__).resolve().parent.parent / "option_a"
sys.path.insert(0, str(OPTION_A))

from check_workflow import expected_settings  # noqa: E402
from fetch_gwosc_frames import destination  # noqa: E402
from pipe_config import (  # noqa: E402
    data_dict_files,
    is_unset,
    needed_window,
    parse_dict,
    read_gps_file,
    read_pipe_ini,
    trigger_time_from_start,
)

SINGLES = {"T3a_gw150914.ini": 1126259462.4, "T3b_gw151012.ini": 1128678900.4}  # GWOSC GPS times
MULTI = "T3c_both.ini"
ALL = [*SINGLES, MULTI]
EVENT_KEYS = {"label", "outdir", "trigger-time", "gps-file"}
IMAGE = "osdf:///igwn/cit/staging/kailibryan.doney/containers/dingo-lensing_1d7c4771b4_recipe-ff6622d_cpu.sif"


def load(name):
    return read_pipe_ini(OPTION_A / name)


class TestT3Configs(unittest.TestCase):
    def test_configs_differ_only_in_how_events_are_given(self):
        for name in ALL[1:]:
            with self.subTest(config=name):
                first, other = load(ALL[0]), load(name)
                differing = {k for k in first.keys() | other.keys() if first.get(k) != other.get(k)}
                self.assertTrue(differing <= EVENT_KEYS, differing)
                self.assertTrue({"label", "outdir"} <= differing)

    def test_labels(self):
        for name in ALL:
            with self.subTest(config=name):
                config = load(name)
                self.assertEqual(config["label"], name.split("_")[0])
                self.assertEqual(config["outdir"], config["label"])

    def test_the_new_image_with_the_fixes(self):
        for name in ALL:
            with self.subTest(config=name):
                self.assertEqual(load(name)["container"], IMAGE)

    def test_t3c_lists_both_singles_events_as_segment_starts(self):
        config = load(MULTI)
        self.assertTrue(is_unset(config, "trigger-time"))
        starts = read_gps_file(OPTION_A / config["gps-file"])
        triggers = [trigger_time_from_start(s, float(config["duration"]), float(config["post-trigger-duration"])) for s in starts]
        self.assertEqual(len(triggers), 2)
        for got, expected in zip(triggers, SINGLES.values()):
            self.assertAlmostEqual(got, expected, places=6)

    def test_singles_give_the_gwosc_trigger_times(self):
        for name, gps in SINGLES.items():
            with self.subTest(config=name):
                self.assertEqual(float(load(name)["trigger-time"]), gps)
                self.assertTrue(is_unset(load(name), "gps-file"))

    def test_data_dict_lists_both_events_frames_per_detector_in_standard_names(self):
        # A list, not a glob: DINGO sets data-dict before transfer-files, so a glob
        # is not expanded at build time and no frame reaches the jobs.
        data = parse_dict(load(MULTI)["data-dict"])
        self.assertEqual(sorted(data), ["H1", "L1"])
        for detector, frames in data.items():
            self.assertEqual(len(frames), 2)
            for frame in frames:
                self.assertTrue(frame.startswith(f"gwosc/{detector[0]}-{detector}_LOSC_4_V1-"), frame)
                self.assertTrue(frame.endswith("-4096.gwf"), frame)
        self.assertTrue(is_unset(load(MULTI), "psd-dict"))  # Each event estimates its own PSD.

    def test_the_two_events_need_different_frame_files(self):
        # Their data windows are 2.4 million seconds apart: No 4096 s file holds both.
        a = needed_window(load("T3a_gw150914.ini"), "H1")
        b = needed_window(load("T3b_gw151012.ini"), "H1")
        self.assertGreater(b[0] - a[1], 4096)


class TestDataDictFiles(unittest.TestCase):
    def test_lists_globs_and_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "gwosc").mkdir()
            for name in ("H-H1_X-200-100.gwf", "H-H1_X-100-100.gwf", "L-L1_X-100-100.gwf"):
                (run / "gwosc" / name).write_text("")
            self.assertEqual(
                data_dict_files("gwosc/H-H1_*.gwf", run), ["gwosc/H-H1_X-100-100.gwf", "gwosc/H-H1_X-200-100.gwf"]
            )
            self.assertEqual(data_dict_files("gwosc/H1.gwf", run), ["gwosc/H1.gwf"])
            self.assertEqual(data_dict_files(["a.gwf", "b.gwf"], run), ["a.gwf", "b.gwf"])
            self.assertEqual(data_dict_files("gwosc/V-V1_*.gwf", run), [])

    def test_workflow_check_expects_every_globbed_frame_for_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            (run / "gwosc").mkdir()
            expected = expected_settings(load(MULTI), run)
            frames = [p for p in expected["generation_inputs"] if p.endswith(".gwf")]
            self.assertEqual(len(frames), 4)
            self.assertIn("gwosc/L-L1_LOSC_4_V1-1128677376-4096.gwf", frames)


class TestFetchDestination(unittest.TestCase):
    URL = "https://gwosc.org/archive/data/O1/1126170624/H-H1_LOSC_4_V1-1126256640-4096.gwf"

    def test_a_plain_path_is_used_as_given(self):
        self.assertEqual(destination("gwosc/H1.gwf", self.URL, Path("/run")), Path("/run/gwosc/H1.gwf"))

    def test_a_glob_keeps_gwoscs_name_in_its_folder(self):
        self.assertEqual(
            destination("gwosc/H-H1_*.gwf", self.URL, Path("/run")),
            Path("/run/gwosc/H-H1_LOSC_4_V1-1126256640-4096.gwf"),
        )

    def test_a_list_names_the_destination(self):
        entry = ["gwosc/H-H1_LOSC_4_V1-1126256640-4096.gwf", "gwosc/H-H1_LOSC_4_V1-1128677376-4096.gwf"]
        self.assertEqual(destination(entry, self.URL, Path("/run")), Path("/run") / entry[0])
        with self.assertRaisesRegex(ValueError, "is not listed"):
            destination(entry[1:], self.URL, Path("/run"))

    def test_a_glob_that_would_not_find_the_file_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            destination("gwosc/L-L1_*.gwf", self.URL, Path("/run"))
        with self.assertRaises(ValueError):
            destination(42, self.URL, Path("/run"))


if __name__ == "__main__":
    unittest.main()
