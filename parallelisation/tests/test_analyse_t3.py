"""Unit tests for the T3 analysis: Two different events, alone and together.

Builds a T3 run folder as launch.sh and bilby_pipe leave it, with DINGO-Lensing's
per-job PSD files, and replaces the two HDF5 readers. Needs numpy and scipy.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "option_a"))

try:
    import analyse_results
    from test_analyse_results import BASE, KINDS, dagman_out, fake_result, job_log

    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False

GPS = {"GW150914": "1126259462-4", "GW151012": "1128678900-4"}
# Which event each (workflow, event index) analyses.
EVENTS = {("T3a", 0): "GW150914", ("T3b", 0): "GW151012", ("T3c", 0): "GW150914", ("T3c", 1): "GW151012"}


def build(root: Path, shared_psds=False, earlier=True):
    """A finished T3 run folder (and, optionally, the first launch's T1a data)."""
    run_dir = root / "T3"
    cluster = 5000
    for label, folder, config, events in analyse_results.T3_WORKFLOWS:
        outdir = run_dir / label
        for sub in ("submit", "result", "data"):
            (outdir / sub).mkdir(parents=True, exist_ok=True)
        (run_dir / config).write_text(f"label = {label}\noutdir = {label}\n")
        (outdir / "submit" / f"dag_{label}.submit.dagman.out").write_text(dagman_out(4 * events))
        dag = []
        for event in range(events):
            gps = GPS[EVENTS[(label, event)]]
            for step, (kind, executable) in enumerate(KINDS):
                name = f"{label}_data{event}_{gps}_{kind}"
                log = f"{label}/log/{name}.log"
                (run_dir / log).parent.mkdir(parents=True, exist_ok=True)
                cluster += 1
                (run_dir / log).write_text(job_log(cluster, BASE + timedelta(seconds=200 * step + 30 * event)))
                (outdir / "submit" / f"{name}.submit").write_text(
                    f"executable = /opt/dingo_env/bin/{executable}\nrequest_cpus = 8\nlog = {log}\nqueue\n"
                )
                dag.append(f"JOB {name}_arg_0 {label}/submit/{name}.submit")
            for suffix in ("_sampling.hdf5", "_importance_sampling.hdf5", "_importance_sampling_plot_corner.pdf"):
                (outdir / "result" / f"{label}_data{event}_{gps}{suffix}").write_text("")
            job = f"{label}_data{event}_{gps}_generation"
            (outdir / "data" / f"{job}_event_data.hdf5").write_text(EVENTS[(label, event)])
            for ifo in ("H1", "L1"):
                (outdir / "data" / f"{job}_{ifo}_psd.txt").write_text(f"{EVENTS[(label, event)]} {ifo}")
        if shared_psds:
            (outdir / "data" / "H1_psd.txt").write_text("")
        (outdir / "submit" / f"dag_{label}.submit").write_text("\n".join(dag) + "\n")
    if earlier:
        data = root / "earlier" / "T1" / "T1a" / "data"
        data.mkdir(parents=True)
        (data / "T1a_data0_1126259462-4_generation_event_data.hdf5").write_text("GW150914")
    return run_dir.parent


def digests_by_content(path):
    """Event data that differ only by event, as the real files should."""
    return {"waveform/H1": Path(path).read_text(), "asds/H1": Path(path).read_text() + " asd"}


def results_by_event(path):
    """Synthetic samples: Every run draws independently (its own seed) from the same distributions."""
    return fake_result(path)


@unittest.skipUnless(HAVE_NUMPY, "needs numpy and scipy")
class TestT3Analysis(unittest.TestCase):
    def analyse(self, digests=digests_by_content, results=results_by_event, **build_options):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = build(Path(directory.name), **build_options)
        with mock.patch.multiple(analyse_results, load_result=mock.DEFAULT, event_data_digests=mock.DEFAULT) as mocks:
            mocks["load_result"].side_effect = results
            mocks["event_data_digests"].side_effect = digests
            return analyse_results.analyse(root, suite="T3", earlier_run_root=root / "earlier")

    def verdicts(self, report):
        return {row["criterion"]: row for row in report["verdicts"]}

    def test_a_good_run_passes_every_criterion(self):
        report = self.analyse()
        for criterion, row in self.verdicts(report).items():
            with self.subTest(criterion=criterion):
                self.assertTrue(row["passed"], row["evidence"])
                self.assertFalse(row["check"], row["evidence"])
        self.assertEqual(report["tests"]["GW150914"]["network_ks"]["runs"], ["T3a", "T3c/0"])
        self.assertEqual(report["tests"]["GW151012"]["network_ks"]["runs"], ["T3b", "T3c/1"])
        self.assertTrue(report["tests"]["GW151012"]["psd_files"]["identical"])
        self.assertEqual(report["different_events"]["runs"], ["T3c/0", "T3c/1"])

    def test_shared_psd_files_fail_t3_2(self):
        report = self.analyse(shared_psds=True)
        row = self.verdicts(report)["T3.2 No output file is written by more than one chain"]
        self.assertFalse(row["passed"])
        self.assertIn("data/H1_psd.txt", row["evidence"])

    def test_event_data_that_differ_from_the_single_run_fail_t3_3(self):
        def changed(path):
            digests = digests_by_content(path)
            if Path(path).name.startswith("T3c_data1_"):
                digests["asds/H1"] = "changed"
            return digests

        verdicts = self.verdicts(self.analyse(digests=changed))
        self.assertFalse(verdicts["T3.3 GW151012 in T3c matches its single-event run"]["passed"])
        self.assertTrue(verdicts["T3.3 GW150914 in T3c matches its single-event run"]["passed"])

    def test_psd_files_from_the_wrong_event_fail_t3_3(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = build(Path(directory.name))
        # As if the last job's PSDs had overwritten event 0's.
        (root / "T3" / "T3c" / "data" / "T3c_data0_1126259462-4_generation_H1_psd.txt").write_text("GW151012 H1")
        with mock.patch.multiple(analyse_results, load_result=mock.DEFAULT, event_data_digests=mock.DEFAULT) as mocks:
            mocks["load_result"].side_effect = results_by_event
            mocks["event_data_digests"].side_effect = digests_by_content
            report = analyse_results.analyse(root, suite="T3")
        row = self.verdicts(report)["T3.3 GW150914 in T3c matches its single-event run"]
        self.assertFalse(row["passed"])
        self.assertIn("PSD files DIFFER for H1", row["evidence"])

    def test_two_events_with_identical_data_fail_t3_4(self):
        verdicts = self.verdicts(self.analyse(digests=lambda path: {"waveform/H1": "same"}))
        self.assertFalse(verdicts["T3.4 The two events' data really differ"]["passed"])

    def test_a_shifted_network_for_one_event_fails_its_comparison(self):
        def shifted(path):
            result = results_by_event(path)
            if Path(path).name.startswith("T3c_data0_") and Path(path).name.endswith("_sampling.hdf5") and "importance" not in Path(path).name:
                result["samples"]["a"] = result["samples"]["a"] + 0.5
            return result

        verdicts = self.verdicts(self.analyse(results=shifted))
        self.assertFalse(verdicts["T3.3 GW150914 in T3c matches its single-event run"]["passed"])
        self.assertTrue(verdicts["T3.3 GW151012 in T3c matches its single-event run"]["passed"])

    def test_the_earlier_t1a_comparison(self):
        verdicts = self.verdicts(self.analyse())
        self.assertIn("Bit-identical", verdicts["Also: GW150914's event data match T1a's from the first launch"]["evidence"])
        report = self.analyse(earlier=False)
        row = self.verdicts(report)["Also: GW150914's event data match T1a's from the first launch"]
        self.assertTrue(row["check"])

    def test_event_data_that_differ_from_t1as_fail_the_earlier_check(self):
        def changed(path):
            digests = digests_by_content(path)
            if Path(path).name.startswith("T1a_"):
                digests["waveform/H1"] = "changed"
            return digests

        row = self.verdicts(self.analyse(digests=changed))["Also: GW150914's event data match T1a's from the first launch"]
        self.assertFalse(row["passed"])
        self.assertIn("DIFFER in waveform/H1", row["evidence"])

    def test_the_t3_report_renders(self):
        report = self.analyse()
        text = analyse_results.render_markdown(report)
        self.assertIn("| T3.2 No output file is written by more than one chain | PASS |", text)
        self.assertIn("## GW151012: Agreement between runs", text)


if __name__ == "__main__":
    unittest.main()
