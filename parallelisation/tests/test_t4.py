"""Unit tests for T4 (seven O4a events: alone, together, and unlensed) and its helpers.

Standard library only, except for two tests: One loads the jobs' frame filter
from the dingo-lensing checkout next to this one, and one needs DINGO (run on
the cluster).
"""
from __future__ import annotations

import hashlib
import http.client
import json
import re
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

PARALLELISATION = Path(__file__).resolve().parent.parent
OPTION_A = PARALLELISATION / "option_a"
MODEL_INFO = PARALLELISATION / "model_info"
sys.path.insert(0, str(OPTION_A))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import make_t4_configs  # noqa: E402
from test_lensing_fixes import MULTI_EVENT, load_multi_event  # noqa: E402

try:
    import check_models

    HAVE_DINGO = True
except ImportError:
    HAVE_DINGO = False
from fetch_gwosc_frames import FRAME_NAME, destinations, frames_for_window  # noqa: E402
from lvk_posteriors import parse_loose_dict  # noqa: E402
from pipe_config import (  # noqa: E402
    data_window,
    is_unset,
    parse_dict,
    read_gps_file,
    read_pipe_ini,
    segment_start,
    trigger_time_from_start,
)
from t4_events import EVENTS, frame_path, frame_starts  # noqa: E402

LENSED = [make_t4_configs.single_name(event) for event in EVENTS]
UNLENSED = [make_t4_configs.single_name(event, True) for event in EVENTS]
MULTI = make_t4_configs.MULTI_CONFIG
ALL = [*LENSED, MULTI, *UNLENSED]
IMAGE = "osdf:///igwn/cit/staging/kailibryan.doney/containers/dingo-lensing_1d7c4771b4_recipe-ff6622d_cpu.sif"
# The 4096 s files each event's data come from, as found in GWOSC's archive on
# 2026-10-14 (GW230628_231200's PSD stretch starts in the file before its event's).
GWOSC_FILES = {
    "GW230628_231200": [1372024832, 1372028928],
    "GW230708_230935": [1372889088],
    "GW230914_111401": [1378721792],
    "GW230927_153832": [1379860480],
    "GW231102_071736": [1382940672],
    "GW231206_233134": [1385938944],
    "GW231206_233901": [1385938944],
}
DURATION, POST_TRIGGER = 8.0, 2.0


def load(name):
    return read_pipe_ini(OPTION_A / name)


def differing(first, second):
    return {key for key in first.keys() | second.keys() if first.get(key) != second.get(key)}


def window(event):
    return data_window(event.trigger_time, DURATION, POST_TRIGGER, 32, 1024.0)


class TestT4Files(unittest.TestCase):
    def test_the_committed_files_are_the_generators_output(self):
        for name, content in make_t4_configs.files().items():
            with self.subTest(file=name):
                path = OPTION_A / name
                self.assertTrue(path.is_file(), f"{name} missing: run make_t4_configs.py")
                # Line endings aside: Git may write CRLF into a Windows checkout.
                text = path.read_bytes().decode().replace("\r\n", "\n")
                self.assertEqual(text, content, f"{name} is out of date: run make_t4_configs.py")

    def test_no_other_t4_files(self):
        written = set(make_t4_configs.files())
        found = {path.name for path in OPTION_A.glob("T4*") if path.suffix in (".ini", ".txt")}
        self.assertEqual(found, written)


class TestT4Events(unittest.TestCase):
    def test_seven_events_in_gps_order(self):
        self.assertEqual([event.letter for event in EVENTS], list("abcdefg"))
        times = [event.trigger_time for event in EVENTS]
        self.assertEqual(times, sorted(times))
        self.assertEqual(len({event.name for event in EVENTS}), 7)

    def test_each_events_data_come_from_the_gwosc_files_checked(self):
        for event in EVENTS:
            with self.subTest(event=event.name):
                self.assertEqual(frame_starts(*window(event)), GWOSC_FILES[event.name])

    def test_no_event_lies_in_anothers_data(self):
        # Another signal in a PSD stretch would inflate that event's noise estimate.
        for event in EVENTS:
            start, end = window(event)
            for other in EVENTS:
                if other is not event:
                    with self.subTest(event=event.name, other=other.name):
                        self.assertFalse(start - 2 <= other.trigger_time <= end + 2)

    def test_two_events_share_a_frame_file_but_not_data(self):
        first, second = (event for event in EVENTS if event.name.startswith("GW231206"))
        self.assertEqual(frame_starts(*window(first)), frame_starts(*window(second)))
        self.assertLess(window(first)[1], window(second)[0])

    def test_frame_paths_are_gwoscs_names(self):
        self.assertEqual(frame_path("H1", 1372024832), "gwosc/H-H1_GWOSC_O4a_4KHZ_R1-1372024832-4096.gwf")
        self.assertEqual(frame_path("L1", 1385938944), "gwosc/L-L1_GWOSC_O4a_4KHZ_R1-1385938944-4096.gwf")
        match = FRAME_NAME.match(Path(frame_path("L1", 1385938944)).name)
        self.assertEqual((match.group("start"), match.group("duration")), ("1385938944", "4096"))

    def test_frame_starts(self):
        self.assertEqual(frame_starts(4096.0, 8192.0), [4096])
        self.assertEqual(frame_starts(4095.5, 4097.0), [0, 4096])
        self.assertEqual(frame_starts(10.0, 20.0), [0])


class TestT4Configs(unittest.TestCase):
    def test_labels_and_outdirs(self):
        for name in ALL:
            with self.subTest(config=name):
                config = load(name)
                self.assertEqual(config["label"], name.split("_")[0])
                self.assertEqual(config["outdir"], config["label"])

    def test_every_config_runs_in_the_image_on_cits_pool(self):
        for name in ALL:
            with self.subTest(config=name):
                config = load(name)
                self.assertEqual(config["container"], IMAGE)
                self.assertEqual(config["conda-env"], "/opt/dingo_env")
                self.assertEqual(config["osg"], "True")
                self.assertEqual(config["extra-lines"], "[requirements = (HAS_SINGULARITY=?=True)]")
                self.assertEqual(config["local"], "False")

    def test_the_multi_event_config_differs_from_the_singles_only_in_its_events(self):
        for name in LENSED:
            with self.subTest(config=name):
                self.assertEqual(
                    differing(load(name), load(MULTI)), {"label", "outdir", "trigger-time", "gps-file", "data-dict"}
                )

    def test_unlensed_configs_differ_from_the_lensed_only_in_the_model(self):
        for lensed, unlensed in zip(LENSED, UNLENSED):
            with self.subTest(config=unlensed):
                self.assertEqual(differing(load(lensed), load(unlensed)), {"label", "outdir", "model"})
                self.assertEqual(load(lensed)["model"], make_t4_configs.LENSED_MODEL)
                self.assertEqual(load(unlensed)["model"], make_t4_configs.UNLENSED_MODEL)

    def test_singles_give_the_events_trigger_times(self):
        for event, name in zip(EVENTS, LENSED):
            with self.subTest(config=name):
                config = load(name)
                self.assertEqual(float(config["trigger-time"]), event.trigger_time)
                self.assertTrue(is_unset(config, "gps-file"))

    def test_the_gps_file_lists_the_events_segment_starts_exactly(self):
        # Trap 2, and exactly: DINGO turns each start back into a trigger time
        # (start + duration - post-trigger duration), and the single runs' event
        # data match T4m's only if that gives the same float.
        config = load(MULTI)
        self.assertTrue(is_unset(config, "trigger-time"))
        starts = read_gps_file(OPTION_A / config["gps-file"])
        self.assertEqual(len(starts), len(EVENTS))
        for event, start in zip(EVENTS, starts):
            with self.subTest(event=event.name):
                self.assertEqual(trigger_time_from_start(start, DURATION, POST_TRIGGER), event.trigger_time)
                self.assertEqual(segment_start(event.trigger_time, DURATION, POST_TRIGGER), start)

    def test_data_dicts_list_the_frames_each_config_needs(self):
        everything = set()
        for event, name in zip(EVENTS, LENSED):
            with self.subTest(config=name):
                data = parse_dict(load(name)["data-dict"])
                self.assertEqual(sorted(data), ["H1", "L1"])
                for detector, files in data.items():
                    self.assertEqual(files, [frame_path(detector, start) for start in GWOSC_FILES[event.name]])
                    everything.update(files)
        multi = parse_dict(load(MULTI)["data-dict"])
        self.assertEqual(sorted(multi["H1"] + multi["L1"]), sorted(everything))
        for files in multi.values():
            self.assertEqual(files, sorted(files))  # In time order, one entry per file.
            self.assertEqual(len(files), len(set(files)))

    def test_data_settings_are_the_models(self):
        # From dingo_ls on both Exercise 3 models (model_info/): 20 to 448 Hz in
        # 0.125 Hz steps (8 s), H1 and L1.
        for model in ("lensed_model_ls.txt", "nonlensed_model_ls.txt"):
            text = (MODEL_INFO / model).read_text()
            with self.subTest(model=model):
                self.assertIn("f_min: 20.0", text)
                self.assertIn("f_max: 448.0", text)
                self.assertIn("delta_f: 0.125", text)
                self.assertIn("detectors:\n    - H1\n    - L1", text)
        for name in ALL:
            with self.subTest(config=name):
                config = load(name)
                self.assertEqual(float(config["duration"]), 1 / 0.125)
                self.assertEqual(float(config["post-trigger-duration"]), POST_TRIGGER)
                self.assertEqual(float(config["minimum-frequency"]), 20.0)
                self.assertEqual(float(config["maximum-frequency"]), 448.0)
                self.assertEqual(int(config["sampling-frequency"]), 1024)
                self.assertEqual(config["detectors"], "[H1, L1]")
                self.assertEqual(parse_dict(config["channel-dict"]), {"H1": "GWOSC-4KHZ_R1_STRAIN", "L1": "GWOSC-4KHZ_R1_STRAIN"})
                self.assertTrue(is_unset(config, "psd-dict"))  # Each event estimates its own PSD.

    def test_the_two_models_share_their_noise_spectra_and_reference_time(self):
        def settings(model):
            text = (MODEL_INFO / model).read_text()
            return (
                re.findall(r"asd_dataset_path: (\S+)", text),
                re.findall(r"ref_time: (\S+)", text),
                re.findall(r"luminosity_distance: (bilby\S+.*)", text),
            )

        self.assertEqual(settings("lensed_model_ls.txt"), settings("nonlensed_model_ls.txt"))
        self.assertEqual(len(settings("lensed_model_ls.txt")[0]), 2)

    def test_requests(self):
        for name in ALL:
            with self.subTest(config=name):
                config = load(name)
                self.assertEqual(int(config["request-cpus"]), 16)
                self.assertEqual(float(config["request-memory"]), 16)  # Room for the 4.5 GB model.
                self.assertEqual(int(config["request-cpus-importance-sampling"]), 32)
                # Model, image and T4m's 14 frame files (about 1.5 GB), plus room for outputs.
                self.assertGreaterEqual(float(config["request-disk"]), 4.5 + 0.8 + 1.6 + 2)


@unittest.skipUnless(MULTI_EVENT.is_file(), "needs the dingo-lensing checkout next to this one")
class TestT4mReadsWhatTheSinglesRead(unittest.TestCase):
    def test_the_jobs_filter_picks_each_events_own_files_from_t4ms_list(self):
        # Each of T4m's data-generation jobs gets every listed file and keeps the
        # ones overlapping its event (dingo_lensing/pipe/multi_event.py): Those
        # must be exactly the files the event's single config lists.
        frames_overlapping = load_multi_event().frames_overlapping
        everything = parse_dict(load(MULTI)["data-dict"])
        for event, name in zip(EVENTS, LENSED):
            single = parse_dict(load(name)["data-dict"])
            for detector in ("H1", "L1"):
                with self.subTest(event=event.name, detector=detector):
                    self.assertEqual(frames_overlapping(everything[detector], *window(event)), single[detector])


@unittest.skipUnless(HAVE_DINGO, "needs DINGO and DINGO-Lensing (run on the cluster)")
class TestCheckModels(unittest.TestCase):
    def test_which_waveform_settings_name_a_lens_model(self):
        # The two Exercise 3 models' settings (model_info/).
        self.assertTrue(check_models.is_lensed({"approximant": "IMRPhenomXPHM", "fdsm_function": "two_images_BBH"}))
        self.assertTrue(check_models.is_lensed({"amplification_factor_function": "two_images_BBH"}))
        self.assertFalse(check_models.is_lensed({"approximant": "IMRPhenomXPHM", "f_ref": 20.0, "spin_conversion_phase": 0.0}))
        self.assertFalse(check_models.is_lensed({"fdsm_function": None}))


class TestLaunchList(unittest.TestCase):
    def test_launch_sh_lists_every_t4_workflow_with_its_builder(self):
        text = (OPTION_A / "launch.sh").read_text()
        block = text[text.index("    T4)") : text.index("    *) fail")]
        entries = [line.strip().strip('"').split() for line in block.splitlines() if line.strip().startswith('"T4')]
        expected = [[name.split("_")[0], "T4", name, "1"] for name in LENSED]
        expected += [["T4m", "T4", MULTI, str(len(EVENTS))]]
        expected += [[name.split("_")[0], "T4", name, "1", "dingo_pipe"] for name in UNLENSED]
        self.assertEqual(entries, expected)


class TestFramesForWindow(unittest.TestCase):
    RUN = "https://gwosc.org/archive/data/O4a_4KHZ_R1/1371537408/"

    def url(self, start, duration=4096):
        return f"{self.RUN}H-H1_GWOSC_O4a_4KHZ_R1-{start}-{duration}.gwf"

    def test_one_file_holds_the_window(self):
        self.assertEqual(frames_for_window([self.url(4096)], 5000, 5300), [self.url(4096)])

    def test_a_window_across_two_files_gets_both_in_order(self):
        urls = [self.url(8192), self.url(4096), self.url(0)]
        self.assertEqual(frames_for_window(urls, 8000, 8300), [self.url(4096), self.url(8192)])

    def test_event_files_and_duplicates_are_dropped(self):
        event = "https://gwosc.org/eventapi/x/H-H1_GWOSC_O4a_4KHZ_R1-4096-4096.gwf"
        urls = [self.url(5000, 32), event, self.url(4096)]
        self.assertEqual(frames_for_window(urls, 5000, 5300), [event])

    def test_a_gap_or_a_short_list_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "do not cover"):
            frames_for_window([self.url(0), self.url(8192)], 4000, 8300)
        with self.assertRaisesRegex(ValueError, "do not cover"):
            frames_for_window([self.url(4096)], 4000, 4300)
        with self.assertRaisesRegex(ValueError, "do not cover"):
            frames_for_window([self.url(5000, 32)], 5000, 5010)

    def test_two_files_need_two_listed_paths(self):
        urls = [self.url(0), self.url(4096)]
        listed = ["gwosc/H-H1_GWOSC_O4a_4KHZ_R1-0-4096.gwf", "gwosc/H-H1_GWOSC_O4a_4KHZ_R1-4096-4096.gwf"]
        self.assertEqual(destinations(listed, urls, Path("/run")), [Path("/run") / path for path in listed])
        with self.assertRaisesRegex(ValueError, "names one path"):
            destinations("gwosc/H1.gwf", urls, Path("/run"))


class FakeResponse:
    """A Zenodo response that may drop the connection after some bytes."""

    def __init__(self, body: bytes, status: int, drop_after: int = None):
        self.body, self.status, self.drop_after, self.sent = body, status, drop_after, 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, size):
        if self.drop_after is not None and self.sent >= self.drop_after:
            raise http.client.IncompleteRead(b"")
        end = len(self.body) if self.drop_after is None else min(len(self.body), self.drop_after)
        block = self.body[self.sent : min(end, self.sent + size)]
        self.sent += len(block)
        return block


class TestReleaseDownload(unittest.TestCase):
    CONTENT = bytes(range(256)) * 20

    def patched(self, name):
        """lvk_posteriors with this content's size and md5 in place of the real file's, and no waiting."""
        import lvk_posteriors

        files = dict(lvk_posteriors.RELEASE_FILES)
        files[name] = (len(self.CONTENT), hashlib.md5(self.CONTENT).hexdigest())
        stack = [
            mock.patch.object(lvk_posteriors, "RELEASE_FILES", files),
            mock.patch.object(lvk_posteriors.time, "sleep"),
        ]
        for patch in stack:
            patch.start()
            self.addCleanup(patch.stop)
        return lvk_posteriors

    def download(self, responses, existing: bytes = None):
        """Run lvk_posteriors.download against scripted responses; return the Range starts asked for."""
        name = EVENTS[0].name
        lvk_posteriors = self.patched(name)
        starts = []

        def urlopen(request, timeout):
            header = request.get_header("Range")
            start = int(header[len("bytes=") : -1]) if header else 0
            starts.append(start)
            response = responses[len(starts) - 1]
            if isinstance(response, Exception):
                raise response
            return response(start)

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / lvk_posteriors.RELEASE_FILE.format(name=name)
        if existing is not None:
            path.write_bytes(existing)
        progress = {}
        with mock.patch.object(lvk_posteriors.urllib.request, "urlopen", urlopen):
            line = lvk_posteriors.download(name, Path(directory.name), progress)
        self.assertEqual(path.read_bytes(), self.CONTENT)
        self.assertIn("md5 matches", line)
        self.assertEqual(progress[name], len(self.CONTENT))
        return starts

    def test_a_dropped_transfer_resumes_where_it_stopped(self):
        content = self.CONTENT
        starts = self.download(
            [
                lambda start: FakeResponse(content, 200, drop_after=1000),
                lambda start: FakeResponse(content[start:], 206),
            ]
        )
        self.assertEqual(starts, [0, 1000])

    def test_a_server_error_is_retried(self):
        content = self.CONTENT
        starts = self.download(
            [
                urllib.error.HTTPError("url", 504, "Gateway Time-out", {}, None),
                lambda start: FakeResponse(content, 200),
            ]
        )
        self.assertEqual(starts, [0, 0])

    def test_a_full_length_copy_with_the_wrong_md5_is_fetched_again(self):
        starts = self.download([lambda start: FakeResponse(self.CONTENT, 200)], existing=b"\0" * len(self.CONTENT))
        self.assertEqual(starts, [0])

    def test_a_copy_longer_than_zenodos_is_fetched_again(self):
        starts = self.download([lambda start: FakeResponse(self.CONTENT, 200)], existing=self.CONTENT + b"extra")
        self.assertEqual(starts, [0])

    def test_a_server_ignoring_the_range_rewrites_the_file(self):
        content = self.CONTENT
        starts = self.download([lambda start: FakeResponse(content, 200)], existing=content[:500])
        self.assertEqual(starts, [500])

    def test_a_complete_copy_is_not_fetched_again(self):
        starts = self.download([], existing=self.CONTENT)
        self.assertEqual(starts, [])

    def test_download_all_reports_every_file_and_exits_on_a_failure(self):
        import io
        import lvk_posteriors

        def fake(name, directory, progress):
            progress[name] = lvk_posteriors.RELEASE_FILES[name][0]
            if name == EVENTS[2].name:
                raise RuntimeError("No copy with Zenodo's size and md5")
            return f"{name}: Done"

        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        output = io.StringIO()
        with mock.patch.object(lvk_posteriors, "download", fake), mock.patch("sys.stdout", output):
            with self.assertRaises(SystemExit) as stopped:
                lvk_posteriors.download_all(Path(directory.name))
        self.assertIn(f"{EVENTS[2].name}: No copy with Zenodo's size and md5", str(stopped.exception))
        for event in EVENTS:
            if event is not EVENTS[2]:
                self.assertIn(f"  {event.name}: Done", output.getvalue())
        self.assertIn("Downloading 7 files (1.42 GB)", output.getvalue())


@unittest.skipUnless((OPTION_A / "t4_lvk.json").is_file(), "no t4_lvk.json yet (launch.sh T4 needs it)")
class TestLvkSummary(unittest.TestCase):
    """t4_lvk.json, from lvk_posteriors.py on the GWTC-4.0 release files."""

    @classmethod
    def setUpClass(cls):
        cls.lvk = json.loads((OPTION_A / "t4_lvk.json").read_text())

    def test_every_event_with_the_trigger_time_the_configs_use(self):
        self.assertEqual(sorted(self.lvk), sorted(event.name for event in EVENTS))
        for event in EVENTS:
            with self.subTest(event=event.name):
                self.assertEqual(self.lvk[event.name]["trigger_time"], event.trigger_time)
                self.assertEqual(float(self.lvk[event.name]["trigger_time_text"]), event.trigger_time)

    def test_the_lvk_analysed_the_same_detectors_segment_and_rate(self):
        for name, entry in self.lvk.items():
            with self.subTest(event=name):
                self.assertEqual(entry["detectors"], ["H1", "L1"])
                self.assertEqual(entry["duration"], DURATION)
                self.assertEqual(entry["post_trigger_duration"], POST_TRIGGER)
                self.assertEqual(entry["sampling_frequency"], 1024.0)
                self.assertEqual(entry["maximum_frequency"]["H1"], 448.0)
                self.assertEqual(entry["maximum_frequency"]["L1"], 448.0)
                self.assertEqual(entry["channel_dict"], {"H1": "GDS-CALIB_STRAIN_CLEAN_AR", "L1": "GDS-CALIB_STRAIN_CLEAN_AR"})

    def test_the_lvk_posteriors_lie_inside_the_models_prior(self):
        for name, entry in self.lvk.items():
            with self.subTest(event=name):
                self.assertGreaterEqual(entry["inside_prior"]["all"], 0.99)
                low, _, high = entry["geocent_time_offset"]
                self.assertLess(max(abs(low), abs(high)), 0.1)


class TestParseLooseDict(unittest.TestCase):
    def test_parse_loose_dict(self):
        self.assertEqual(parse_loose_dict("{ H1:40,L1:30, waveform: 13.33  }"), {"H1": 40.0, "L1": 30.0, "waveform": 13.33})
        self.assertEqual(parse_loose_dict("{ H1:H1_HOFT_C00_AR,L1:L1_HOFT_C00_AR, }"), {"H1": "H1_HOFT_C00_AR", "L1": "L1_HOFT_C00_AR"})
        self.assertEqual(parse_loose_dict("20"), {"all": 20.0})
        with self.assertRaises(ValueError):
            parse_loose_dict("{ H1 40 }")


if __name__ == "__main__":
    unittest.main()
