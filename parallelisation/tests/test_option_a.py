"""Unit tests for the option A setup: helper functions, configs and GPS files.

These turn the desk-check traps (see ../test_log.md) into checks. launch.sh
runs this file before anything else and stops if any test fails. Standard
library only, so it runs on the cluster and on a machine without DINGO.
"""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

PARALLELISATION = Path(__file__).resolve().parent.parent
OPTION_A = PARALLELISATION / "option_a"
TUTORIAL = PARALLELISATION / "tutorial_reference"
sys.path.insert(0, str(OPTION_A))

from fetch_gwosc_frames import channel_names_in  # noqa: E402
from check_workflow import requirements_override  # noqa: E402
from pipe_config import (  # noqa: E402
    data_window,
    is_unset,
    needed_window,
    parse_dict,
    read_gps_file,
    read_pipe_ini,
    segment_start,
    trigger_time_from_start,
)

IMAGE_ENV = "/opt/dingo_env"
STAGED_IMAGES = "osdf:///igwn/cit/staging/kailibryan.doney/containers/"
# The image's own requirement, replacing DINGO's remote-pool (IS_GLIDEIN) one.
REQUIREMENTS_OVERRIDE = "(HAS_SINGULARITY=?=True)"
SINGLE_CONFIGS = {"T1": "T1a_single.ini", "T2": "T2a_single.ini"}
# Test -> (config, GPS file, number of events listed).
MULTI_CONFIGS = {
    "T1": ("T1b_twice.ini", "T1b_gps.txt", 2),
    "T2": ("T2b_three.ini", "T2b_gps.txt", 3),
}
ALL_CONFIGS = [
    "T1a_single.ini",
    "T1b_twice.ini",
    "T2a_single.ini",
    "T2b_three.ini",
]
# The only keys allowed to differ between a test's single and multi config.
EVENT_KEYS = {"label", "outdir", "trigger-time", "gps-file"}


def load(name: str) -> dict:
    return read_pipe_ini(OPTION_A / name)


def differing_keys(first: dict, second: dict) -> set:
    return {
        key
        for key in first.keys() | second.keys()
        if first.get(key) != second.get(key)
    }


class TestReadPipeIni(unittest.TestCase):
    def write(self, text: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "config.ini"
        path.write_text(text)
        return path

    def test_reads_entries_and_skips_comments_sections_and_blank_lines(self):
        path = self.write(
            "# comment\n[section]\n\nlocal = False\nmodel=/a/b.pt\n"
            "data-dict = {'H1': 'x.gwf'}\n"
        )
        self.assertEqual(
            read_pipe_ini(path),
            {"local": "False", "model": "/a/b.pt", "data-dict": "{'H1': 'x.gwf'}"},
        )

    def test_underscores_in_keys_become_hyphens(self):
        path = self.write("trigger_time = 1.0\n")
        self.assertEqual(read_pipe_ini(path), {"trigger-time": "1.0"})

    def test_windows_line_endings_are_handled(self):
        path = self.write("local = False\r\nlabel = T1a\r\n")
        self.assertEqual(read_pipe_ini(path), {"local": "False", "label": "T1a"})

    def test_duplicate_key_is_an_error(self):
        path = self.write("label = a\ntrigger_time = 1\ntrigger-time = 2\n")
        with self.assertRaisesRegex(ValueError, "Duplicate key 'trigger-time'"):
            read_pipe_ini(path)

    def test_line_without_equals_is_an_error(self):
        path = self.write("local False\n")
        with self.assertRaisesRegex(ValueError, "Expected 'key = value'"):
            read_pipe_ini(path)


class TestValueHelpers(unittest.TestCase):
    def test_is_unset(self):
        entries = {"psd-dict": "None", "psd-start-time": "none", "label": "T1a"}
        self.assertTrue(is_unset(entries, "psd-dict"))
        self.assertTrue(is_unset(entries, "psd-start-time"))
        self.assertTrue(is_unset(entries, "gps-file"))
        self.assertFalse(is_unset(entries, "label"))

    def test_parse_dict_accepts_single_and_double_quotes(self):
        self.assertEqual(
            parse_dict("{'H1': 'gwosc/H1.gwf', \"L1\": \"gwosc/L1.gwf\"}"),
            {"H1": "gwosc/H1.gwf", "L1": "gwosc/L1.gwf"},
        )

    def test_parse_dict_rejects_non_dicts(self):
        with self.assertRaises(ValueError):
            parse_dict("['H1', 'L1']")


class TestReadGpsFile(unittest.TestCase):
    def test_takes_first_column_and_skips_comments(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "gps.txt"
        path.write_text("# header\n100.5\n200.25, 7  # trailing comment\n\n300\n")
        self.assertEqual(read_gps_file(path), [100.5, 200.25, 300.0])


class TestChannelNamesIn(unittest.TestCase):
    def test_finds_each_channel_of_the_detector_once_in_raw_bytes(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "frame.gwf"
        path.write_bytes(
            b"\x00\x07H1:LOSC-STRAIN\x00\xffH1:LOSC-DQMASK\x01"
            b"H1:LOSC-STRAIN\x00L1:LOSC-STRAIN\x00"
        )
        self.assertEqual(
            channel_names_in(path, "H1"), ["H1:LOSC-DQMASK", "H1:LOSC-STRAIN"]
        )
        self.assertEqual(channel_names_in(path, "V1"), [])


class TestSegmentArithmetic(unittest.TestCase):
    def test_segment_start_for_the_test_events(self):
        self.assertAlmostEqual(segment_start(1126259462.4, 4.0, 2.0), 1126259460.4, places=6)
        self.assertAlmostEqual(segment_start(1384782888.63, 8.0, 2.0), 1384782882.63, places=6)

    def test_trigger_time_from_start_inverts_segment_start(self):
        for trigger, duration, post in [(1126259462.4, 4.0, 2.0), (1384782888.63, 8.0, 2.0), (1e9, 64.0, 0.5)]:
            start = segment_start(trigger, duration, post)
            self.assertAlmostEqual(trigger_time_from_start(start, duration, post), trigger, places=6)

    def test_data_window_covers_psd_stretch_and_segment(self):
        start, end = data_window(1126259462.4, 4.0, 2.0, 128)
        self.assertAlmostEqual(start, 1126259460.4 - 512.0, places=6)
        self.assertAlmostEqual(end, 1126259464.4, places=6)

    def test_data_window_caps_psd_stretch_at_maximum(self):
        start, _ = data_window(1126259462.4, 4.0, 2.0, 512, psd_maximum_duration=1024.0)
        self.assertAlmostEqual(start, 1126259460.4 - 1024.0, places=6)


class TestNeededWindow(unittest.TestCase):
    SINGLE = {
        "trigger-time": "1000.0",
        "duration": "8.0",
        "post-trigger-duration": "2.0",
        "psd-length": "32",
        "psd-maximum-duration": "1024",
    }

    def window(self, detector="H1", **changes):
        entries = dict(self.SINGLE)
        entries.update({key.replace("_", "-"): value for key, value in changes.items()})
        return needed_window(entries, detector)

    def test_without_psd_files_the_psd_stretch_comes_first(self):
        # Segment 994 to 1002, after min(32 * 8, 1024) = 256 s of PSD data.
        self.assertEqual(self.window(), (994.0 - 256.0, 1002.0))

    def test_with_a_psd_file_only_the_segment_is_read(self):
        psd_dict = "{'H1': '/a/H1_psd.txt', 'L1': '/a/L1_psd.txt'}"
        self.assertEqual(self.window(psd_dict=psd_dict), (994.0, 1002.0))

    def test_psd_files_count_per_detector(self):
        psd_dict = "{'H1': '/a/H1_psd.txt', 'L1': None}"
        self.assertEqual(self.window("H1", psd_dict=psd_dict), (994.0, 1002.0))
        self.assertEqual(self.window("L1", psd_dict=psd_dict), (994.0 - 256.0, 1002.0))
        self.assertEqual(self.window("V1", psd_dict=psd_dict), (994.0 - 256.0, 1002.0))

    def test_psd_dict_given_as_none_means_no_psd_files(self):
        self.assertEqual(self.window(psd_dict="None"), (994.0 - 256.0, 1002.0))

    def test_needs_a_trigger_time(self):
        with self.assertRaisesRegex(ValueError, "single-event"):
            self.window(trigger_time="None")

    def test_rejects_a_custom_psd_start_time(self):
        with self.assertRaisesRegex(ValueError, "psd-start-time"):
            self.window(psd_start_time="-100")

    def test_the_test_configs(self):
        t1a = load("T1a_single.ini")
        t2a = load("T2a_single.ini")
        for detector in ("H1", "L1"):
            with self.subTest(detector=detector):
                # T1 estimates PSDs from 128 x 4 s before its segment; T2 has PSD files.
                start, end = needed_window(t1a, detector)
                self.assertAlmostEqual(start, 1126259460.4 - 512.0, places=6)
                self.assertAlmostEqual(end, 1126259464.4, places=6)
                start, end = needed_window(t2a, detector)
                self.assertAlmostEqual(start, 1384782882.63, places=6)
                self.assertAlmostEqual(end, 1384782890.63, places=6)


class TestOptionAConfigs(unittest.TestCase):
    def test_every_config_runs_on_condor_inside_a_staged_image(self):
        # Trap 5: conda-env decides which code the jobs run; with a container,
        # it names the environment inside the image.
        for name in ALL_CONFIGS:
            with self.subTest(config=name):
                config = load(name)
                self.assertEqual(config["local"], "False")
                self.assertEqual(config["scheduler"], "condor")
                self.assertEqual(config["conda-env"], IMAGE_ENV)
                self.assertTrue(config["container"].startswith(STAGED_IMAGES), config["container"])
                self.assertTrue(config["container"].endswith("_cpu.sif"), config["container"])

    def test_every_config_uses_the_same_image(self):
        self.assertEqual(len({load(name)["container"] for name in ALL_CONFIGS}), 1)

    def test_every_config_sends_the_image_to_every_job(self):
        # DINGO's sampling and importance-sampling jobs receive the image only in osg mode.
        for name in ALL_CONFIGS:
            with self.subTest(config=name):
                self.assertEqual(load(name)["osg"], "True")

    def test_every_config_keeps_every_job_on_cits_pool(self):
        # osg mode adds IS_GLIDEIN=?=True to sampling and importance-sampling jobs;
        # the override replaces it. bilby_pipe splits list values on commas, so the
        # requirement must stay one entry.
        for name in ALL_CONFIGS:
            with self.subTest(config=name):
                config = load(name)
                self.assertIn("extra-lines", config, "No requirements override")
                raw = config["extra-lines"]
                self.assertTrue(raw.startswith("[") and raw.endswith("]"), raw)
                entries = [entry.strip() for entry in raw[1:-1].split(",")]
                self.assertEqual(entries, [f"requirements = {REQUIREMENTS_OVERRIDE}"])
                self.assertEqual(requirements_override(config), REQUIREMENTS_OVERRIDE)

    def test_t2_asks_for_disk_for_the_model_and_the_image(self):
        # Data-generation and sampling jobs receive the 4.5 GB model and the
        # 0.8 GB image; launch.sh checks the real sizes. Leave room for outputs.
        for name in ("T2a_single.ini", "T2b_three.ini"):
            with self.subTest(config=name):
                self.assertGreaterEqual(float(load(name)["request-disk"]), 4.5 + 0.8 + 2)

    def test_single_event_configs_give_a_trigger_time_and_no_gps_file(self):
        for name in SINGLE_CONFIGS.values():
            with self.subTest(config=name):
                config = load(name)
                self.assertFalse(is_unset(config, "trigger-time"))
                self.assertTrue(is_unset(config, "gps-file"))

    def test_multi_event_configs_give_a_gps_file_and_no_trigger_time(self):
        # Trap 1: A trigger-time would make bilby_pipe ignore the gps-file.
        for name, gps_file, _ in MULTI_CONFIGS.values():
            with self.subTest(config=name):
                config = load(name)
                self.assertTrue(is_unset(config, "trigger-time"))
                self.assertEqual(config["gps-file"], gps_file)

    def test_gps_files_list_the_single_events_segment_start(self):
        # Trap 2: The gps-file holds segment start times, not trigger times.
        for test, (name, gps_file, n_events) in MULTI_CONFIGS.items():
            with self.subTest(test=test):
                config = load(name)
                trigger = float(load(SINGLE_CONFIGS[test])["trigger-time"])
                starts = read_gps_file(OPTION_A / gps_file)
                self.assertEqual(len(starts), n_events)
                for start in starts:
                    self.assertAlmostEqual(
                        trigger_time_from_start(
                            start,
                            float(config["duration"]),
                            float(config["post-trigger-duration"]),
                        ),
                        trigger,
                        places=6,
                    )

    def test_single_and_multi_configs_differ_only_in_how_events_are_given(self):
        for test, (name, _, _) in MULTI_CONFIGS.items():
            with self.subTest(test=test):
                differences = differing_keys(load(SINGLE_CONFIGS[test]), load(name))
                self.assertEqual(differences, EVENT_KEYS)

    def test_labels_match_outdirs_and_are_unique(self):
        labels = []
        for name in ALL_CONFIGS:
            with self.subTest(config=name):
                config = load(name)
                self.assertEqual(config["label"], name.split("_")[0])
                self.assertEqual(config["outdir"], config["label"])
                labels.append(config["label"])
        self.assertEqual(len(labels), len(set(labels)))

    def test_importance_sampling_is_not_split(self):
        # n-parallel > 1 needs the merge step, which is broken for lensed runs.
        for name in ALL_CONFIGS:
            with self.subTest(config=name):
                config = load(name)
                self.assertTrue(
                    is_unset(config, "n-parallel") or config["n-parallel"] == "1"
                )

    def test_t2a_is_the_tutorial_config_apart_from_the_planned_changes(self):
        tutorial = read_pipe_ini(
            TUTORIAL / "ex3_dingo_lensing_application" / "dingo_pipe_lensed.ini"
        )
        t2a = load("T2a_single.ini")
        self.assertEqual(
            differing_keys(tutorial, t2a),
            {
                "local",
                "label",
                "outdir",
                "conda-env",
                "container",
                "osg",
                "extra-lines",
                "request-disk",
            },
        )
        self.assertEqual(t2a["local"], "False")

    def test_t1_duration_matches_the_toy_models_training_domain(self):
        # dingo_pipe takes the duration from the model; T1 states it explicitly,
        # so it must equal 1 / delta_f of Exercise 2's training dataset.
        settings = (
            TUTORIAL / "ex2_dingo_lensing" / "waveform_dataset_settings_two_images_BBH.yaml"
        ).read_text()
        delta_f = float(re.search(r"^\s*delta_f:\s*([0-9.]+)", settings, re.M).group(1))
        for name in ("T1a_single.ini", "T1b_twice.ini"):
            with self.subTest(config=name):
                self.assertEqual(float(load(name)["duration"]), 1.0 / delta_f)

    def test_t1_data_and_channels_cover_both_detectors(self):
        for name in ("T1a_single.ini", "T1b_twice.ini"):
            with self.subTest(config=name):
                config = load(name)
                self.assertEqual(set(parse_dict(config["data-dict"])), {"H1", "L1"})
                self.assertEqual(set(parse_dict(config["channel-dict"])), {"H1", "L1"})
                self.assertTrue(is_unset(config, "psd-dict"))


if __name__ == "__main__":
    unittest.main()
