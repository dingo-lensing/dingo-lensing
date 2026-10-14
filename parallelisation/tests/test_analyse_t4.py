"""Unit tests for the T4 analysis: Seven events alone, together, and through the unlensed model.

Builds a T4 run folder as launch.sh, dingo_lensing_pipe and dingo_pipe leave it
(the unlensed runs with DINGO's own PSD file names) and replaces the two HDF5
readers. Needs numpy and scipy.
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
import zlib
from datetime import timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "option_a"))

import make_t4_configs  # noqa: E402
from t4_events import EVENTS  # noqa: E402

try:
    import numpy as np

    import analyse_results
    from test_analyse_results import BASE, KINDS, dagman_out, job_log
    from test_analyse_t3 import arrays_by_content, write_psd

    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False

DINGO_KINDS = [
    ("generation", "dingo_pipe_generation"),
    ("sampling", "dingo_pipe_sampling"),
    ("importance_sampling", "dingo_pipe_importance_sampling"),
    ("importance_sampling_plot", "dingo_pipe_plot"),
]


def event_for(label: str, index: int):
    """Which event a workflow's event index analyses."""
    if label == "T4m":
        return EVENTS[index]
    return next(event for event in EVENTS if event.letter == label[-1])


def gps_text(trigger_time: float) -> str:
    """The trigger time as bilby_pipe writes it in job labels."""
    return str(trigger_time).replace(".", "-")


def build(root: Path) -> Path:
    """A finished T4 run folder."""
    run_dir = root / "T4"
    cluster = 9000
    for label, folder, config, events in analyse_results.T4_WORKFLOWS:
        unlensed = label.startswith("T4u")
        outdir = run_dir / label
        for sub in ("submit", "result", "data"):
            (outdir / sub).mkdir(parents=True, exist_ok=True)
        (run_dir / config).write_text(f"label = {label}\noutdir = {label}\n")
        (outdir / "submit" / f"dag_{label}.submit.dagman.out").write_text(dagman_out(4 * events))
        dag = []
        for index in range(events):
            event = event_for(label, index)
            gps = gps_text(event.trigger_time)
            for step, (kind, executable) in enumerate(DINGO_KINDS if unlensed else KINDS):
                name = f"{label}_data{index}_{gps}_{kind}"
                log = f"{label}/log/{name}.log"
                (run_dir / log).parent.mkdir(parents=True, exist_ok=True)
                cluster += 1
                (run_dir / log).write_text(job_log(cluster, BASE + timedelta(seconds=200 * step + 30 * index)))
                (outdir / "submit" / f"{name}.submit").write_text(
                    f"executable = /opt/dingo_env/bin/{executable}\nrequest_cpus = 16\nlog = {log}\nqueue\n"
                )
                dag.append(f"JOB {name}_arg_0 {label}/submit/{name}.submit")
            for suffix in ("_sampling.hdf5", "_importance_sampling.hdf5", "_importance_sampling_plot_corner.pdf"):
                (outdir / "result" / f"{label}_data{index}_{gps}{suffix}").write_text("")
            job = f"{label}_data{index}_{gps}_generation"
            (outdir / "data" / f"{job}_event_data.hdf5").write_text(event.name)
            for ifo in ("H1", "L1"):
                # DINGO writes data/<detector>_psd.txt; DINGO-Lensing names the job.
                psd = f"{ifo}_psd.txt" if unlensed else f"{job}_{ifo}_psd.txt"
                write_psd(outdir / "data" / psd, event.name, ifo)
        (outdir / "submit" / f"dag_{label}.submit").write_text("\n".join(dag) + "\n")
    (root / "run_metadata.txt").write_text("date: 2026-10-14T12:00:00Z\nsuite: T4\n")
    return root


def t4_result(path, log_evidence=None, weights=None) -> dict:
    """Synthetic DINGO results: Every run draws independently (its own seed) from the same distributions."""
    path = Path(path)
    rng = np.random.default_rng(zlib.crc32(path.name.encode()))
    n = 2000
    samples = {
        "chirp_mass": rng.normal(40.0, 1.0, n),
        "mass_ratio": rng.uniform(0.5, 1.0, n),
        "luminosity_distance": rng.normal(2000.0, 300.0, n),
        "a_1": rng.uniform(0.0, 0.9, n),
        "a_2": rng.uniform(0.0, 0.9, n),
        "tilt_1": rng.uniform(0.0, math.pi, n),
        "tilt_2": rng.uniform(0.0, math.pi, n),
        "log_prob": rng.normal(-10.0, 3.0, n),
    }
    if not path.name.startswith("T4u"):
        samples.update(lensing_delta_t=rng.uniform(0.0, 0.1, n), mu_rel=rng.uniform(0.0, 1.0, n))
    if not path.name.endswith("_importance_sampling.hdf5"):
        return {"samples": samples, "log_evidence": None}
    samples.update(
        weights=rng.uniform(0.5, 1.5, n) if weights is None else weights,
        log_likelihood=rng.normal(size=n),
        log_prior=rng.normal(size=n),
    )
    if log_evidence is None:
        log_evidence = -100.0 + 0.001 * (zlib.crc32(path.name.encode()) % 3)
    return {"samples": samples, "log_evidence": log_evidence}


def lvk_summary(path: Path, chirp_mass_medians=None) -> Path:
    """A t4_lvk.json whose posteriors match the synthetic runs."""
    entries = {}
    for event in EVENTS:
        median = (chirp_mass_medians or {}).get(event.name, 40.0)
        entries[event.name] = {
            "quantiles": {
                "chirp_mass": [median - 2.0, median, median + 2.0],
                "mass_ratio": [0.55, 0.75, 0.95],
                "luminosity_distance": [1500.0, 2000.0, 2500.0],
                "chi_eff": [-0.2, 0.0, 0.2],
            },
            "minimum_frequency": {"H1": 20.0, "L1": 20.0, "waveform": 13.33},
        }
    path.write_text(json.dumps(entries))
    return path


@unittest.skipUnless(HAVE_NUMPY, "needs numpy and scipy")
class TestT4Analysis(unittest.TestCase):
    def analyse(self, results=t4_result, arrays=arrays_by_content, lvk=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = build(Path(directory.name))
        lvk = lvk_summary(root / "t4_lvk.json") if lvk is None else lvk
        with mock.patch.multiple(analyse_results, load_result=mock.DEFAULT, event_data_arrays=mock.DEFAULT) as mocks:
            mocks["load_result"].side_effect = results
            mocks["event_data_arrays"].side_effect = arrays
            return analyse_results.analyse(root, suite="T4", lvk_summary=lvk)

    def verdicts(self, report):
        return {row["criterion"]: row for row in report["verdicts"]}

    def test_a_good_run_passes_every_criterion(self):
        report = self.analyse()
        verdicts = self.verdicts(report)
        self.assertEqual(len(verdicts), 1 + 1 + 7 + 1 + 1 + 1 + 1 + 2)
        for criterion, row in verdicts.items():
            with self.subTest(criterion=criterion):
                self.assertTrue(row["passed"], row["evidence"])
                self.assertFalse(row["check"], row["evidence"])
        for index, event in enumerate(EVENTS):
            self.assertEqual(report["tests"][event.name]["network_ks"]["runs"], [f"T4{event.letter}", f"T4m/{index}"])
            # A 1% chance of any false alarm over all seven events, not 1% each.
            self.assertAlmostEqual(report["tests"][event.name]["network_ks"]["alpha"], 0.01 / 7)
        self.assertEqual(report["different_events"]["pairs"], 21)
        for row in report["bayes_factors"].values():
            self.assertTrue(row["reliable"])
            self.assertLess(abs(row["log10_B"]), 0.01)

    def test_every_job_of_both_builders_is_timed(self):
        report = self.analyse()
        for label in ("T4a", "T4m", "T4ua"):
            kinds = {row["kind"] for row in report["workflows"][label]["jobs"]}
            self.assertEqual(kinds, {"generation", "sampling", "importance sampling", "plot"}, label)

    def test_the_bayes_factor_is_the_difference_of_log_evidences(self):
        def results(path):
            name = Path(path).name
            if name.startswith("T4a_") and name.endswith("_importance_sampling.hdf5"):
                return t4_result(path, log_evidence=-95.0)
            if name.startswith("T4ua_") and name.endswith("_importance_sampling.hdf5"):
                return t4_result(path, log_evidence=-100.0)
            return t4_result(path)

        report = self.analyse(results=results)
        row = report["bayes_factors"][EVENTS[0].name]
        self.assertAlmostEqual(row["ln_B"], 5.0)
        self.assertAlmostEqual(row["log10_B"], 5.0 / math.log(10))
        self.assertAlmostEqual(row["log10_B_std"] * math.log(10), row["ln_B_std"])
        verdict = self.verdicts(report)["Also: Lensing Bayes factors, log10 B (lensed vs unlensed)"]
        self.assertTrue(verdict["check"])
        self.assertIn(f"{EVENTS[0].name} +2.17", verdict["evidence"])
        # T4m's run of the event still has the old evidence, so T4.3 notices the single run's.
        self.assertFalse(self.verdicts(report)[f"T4.3 {EVENTS[0].name} in T4m matches its single-event run"]["passed"])

    def test_few_effective_samples_make_the_bayes_factor_unreliable(self):
        def results(path):
            name = Path(path).name
            if name.startswith("T4ub_") and name.endswith("_importance_sampling.hdf5"):
                weights = np.full(2000, 1e-9)
                weights[:20] = 1.0  # 20 effective samples.
                return t4_result(path, weights=weights)
            return t4_result(path)

        report = self.analyse(results=results)
        verdicts = self.verdicts(report)
        row = verdicts["T4.7 Importance sampling gives at least 100 effective samples in every run"]
        self.assertTrue(row["passed"])
        self.assertTrue(row["check"])
        self.assertIn("T4ub (20.0)", row["evidence"])
        self.assertFalse(report["bayes_factors"][EVENTS[1].name]["reliable"])
        self.assertTrue(verdicts["Also: Lensing Bayes factors, log10 B (lensed vs unlensed)"]["check"])

    def test_lensed_and_unlensed_runs_must_see_the_same_data(self):
        def arrays(path):
            content = arrays_by_content(path)
            if Path(path).name.startswith("T4uc_"):
                content["asds/H1"] = content["asds/H1"] * 1.001
            return content

        row = self.verdicts(self.analyse(arrays=arrays))["T4.5 Each event's lensed and unlensed runs analyse the same data"]
        self.assertFalse(row["passed"])
        self.assertIn(f"{EVENTS[2].name}: event data DIFFER in asds/H1", row["evidence"])

    def test_round_off_between_lensed_and_unlensed_data_passes(self):
        def arrays(path):
            content = arrays_by_content(path)
            if Path(path).name.startswith("T4ud_"):
                content["waveform/H1"] = content["waveform/H1"] * (1 + 3e-16)
            return content

        row = self.verdicts(self.analyse(arrays=arrays))["T4.5 Each event's lensed and unlensed runs analyse the same data"]
        self.assertTrue(row["passed"], row["evidence"])
        self.assertIn(f"{EVENTS[3].name}: event data equal to within round-off", row["evidence"])

    def test_events_with_the_same_data_fail_t4_4(self):
        verdicts = self.verdicts(self.analyse(arrays=lambda path: {"waveform/H1": np.ones(4)}))
        row = verdicts["T4.4 The seven events' data really differ"]
        self.assertFalse(row["passed"])
        self.assertIn("The same data for T4m/0 and T4m/1", row["evidence"])

    def test_a_chirp_mass_unlike_the_lvks_is_flagged(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        lvk = lvk_summary(Path(directory.name) / "lvk.json", {EVENTS[4].name: 60.0})
        report = self.analyse(lvk=lvk)
        row = self.verdicts(report)["Also: Detector-frame chirp mass agrees with the LVK's GWTC-4.0 results"]
        self.assertTrue(row["check"])
        self.assertIn(f"{EVENTS[4].name}: LVK median chirp mass outside the 90% interval of T4e, T4ue", row["evidence"])

    def test_no_lvk_summary_is_flagged(self):
        report = self.analyse(lvk=Path("does-not-exist.json"))
        row = self.verdicts(report)["Also: Detector-frame chirp mass agrees with the LVK's GWTC-4.0 results"]
        self.assertTrue(row["check"])
        self.assertIn("no LVK summary", row["evidence"])

    def test_chi_eff_from_spins(self):
        samples = {
            "mass_ratio": np.array([1.0, 0.5]),
            "a_1": np.array([0.5, 0.4]),
            "a_2": np.array([0.5, 0.2]),
            "tilt_1": np.array([0.0, 0.0]),
            "tilt_2": np.array([math.pi, 0.0]),
        }
        chi_eff = analyse_results.with_chi_eff(samples)["chi_eff"]
        np.testing.assert_allclose(chi_eff, [0.0, (0.4 + 0.5 * 0.2) / 1.5])

    def test_the_t4_report_renders(self):
        text = analyse_results.render_markdown(self.analyse())
        self.assertIn("| T4.2 No output file is written by more than one chain | PASS |", text)
        self.assertIn("## Lensing Bayes factors", text)
        self.assertIn("## Comparison with GWTC-4.0", text)
        self.assertIn(f"**{EVENTS[0].name}** (LVK's lowest frequency: H1 20 Hz, L1 20 Hz)", text)
        self.assertIn(f"## {EVENTS[6].name}: Agreement between runs", text)


@unittest.skipUnless(HAVE_NUMPY, "needs numpy and scipy")
class TestT4Lists(unittest.TestCase):
    def test_the_analysis_reads_the_workflows_the_configs_define(self):
        workflows = analyse_results.T4_WORKFLOWS
        expected = [(f"T4{e.letter}", make_t4_configs.single_name(e)) for e in EVENTS]
        expected += [("T4m", make_t4_configs.MULTI_CONFIG)]
        expected += [(f"T4u{e.letter}", make_t4_configs.single_name(e, True)) for e in EVENTS]
        self.assertEqual([(label, config) for label, _, config, _ in workflows], expected)
        self.assertEqual([events for _, _, _, events in workflows], [1] * 7 + [7] + [1] * 7)
        self.assertEqual({folder for _, folder, _, _ in workflows}, {"T4"})

    def test_t4m_event_indices_follow_the_gps_file(self):
        for index, event in enumerate(EVENTS):
            self.assertEqual(analyse_results.T4_GROUPS[event.name], [(f"T4{event.letter}", 0), ("T4m", index)])


if __name__ == "__main__":
    unittest.main()
