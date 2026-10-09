"""Unit tests for analyse_results.py: Statistics, run-folder checks and the report.

The run folder is laid out here as launch.sh and bilby_pipe leave it (DAG,
submit files, Condor logs, result files), with load_result replaced by
synthetic samples, so everything except reading HDF5 runs without the cluster.
Needs numpy and scipy, as the analysis does.
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
import zlib
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "option_a"))

try:
    import numpy as np
    import scipy  # noqa: F401

    import analyse_results
    from analyse_results import (
        WORKFLOWS,
        completion,
        duration,
        evidence_comparison,
        importance_summary,
        ks_comparison,
        render_markdown,
        result_files,
        shared_outputs,
        to_json,
        weighted_quantiles,
        workflow_timing,
    )

    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False

needs_numpy = unittest.skipUnless(HAVE_NUMPY, "needs numpy and scipy")

KINDS = [
    ("generation", "dingo_lensing_pipe_generation"),
    ("sampling", "dingo_lensing_pipe_sampling"),
    ("importance_sampling", "dingo_lensing_pipe_importance_sampling"),
    ("importance_sampling_plot", "dingo_pipe_plot"),
]
BASE = datetime(2026, 10, 8, 8, 39, 56)
REFERENCE_LOG_EVIDENCE = -5829.945


def stamp(time: datetime) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def job_log(cluster: int, submitted: datetime, cpu_minutes: int = 2) -> str:
    """A successful job's event log, in CIT's format."""
    events = [
        (submitted, "000", "Job submitted from host: <131.215.5.225:9618>", []),
        (submitted + timedelta(seconds=10), "040", "Started transferring input files", []),
        (submitted + timedelta(seconds=20), "040", "Finished transferring input files", []),
        (submitted + timedelta(seconds=20), "001", "Job executing on host: <10.0.0.1:9618?alias=node1.cluster.ldas.cit&x>", []),
        (
            submitted + timedelta(seconds=140),
            "005",
            "Job terminated.",
            [
                "\t(1) Normal termination (return value 0)",
                f"\t\tUsr 0 00:{cpu_minutes:02d}:00, Sys 0 00:00:00  -  Run Remote Usage",
                "\t1000  -  Run Bytes Received By Job",
                "\tPartitionable Resources :    Usage  Request Allocated ",
                "\t   Cpus                 :     1.00        8         8 ",
                "\t   Disk (KB)            :  1000000  5242880   5242880 ",
                "\t   Memory (MB)          :     1000     8192      8192 ",
            ],
        ),
    ]
    lines = []
    for time, code, text, body in events:
        lines += [f"{code} ({cluster}.000.000) {stamp(time)} {text}", *body, "..."]
    return "\n".join(lines) + "\n"


def dagman_out(nodes: int, status: int = 0) -> str:
    failed = 0 if status == 0 else 1
    return (
        f"10/08/26 08:46:59 DAG status: {status} (DAG_STATUS_{'OK' if status == 0 else 'NODE_FAILED'})\n"
        f"10/08/26 08:46:59 Of {nodes} nodes total:\n"
        "10/08/26 08:46:59  Done     Pre   Queued    Post   Ready   Un-Ready   Failed   Futile\n"
        "10/08/26 08:46:59   ===     ===      ===     ===     ===        ===      ===      ===\n"
        f"10/08/26 08:46:59    {nodes - failed}       0        0       0       0          0        {failed}        0\n"
        f"10/08/26 08:46:59 **** condor_dagman (condor_DAGMAN) pid 1 EXITING WITH STATUS {status}\n"
    )


class RunRoot:
    """An option A run folder after all four workflows have finished."""

    def __init__(self, root: Path, psd_files: bool = True):
        self.root = root
        cluster = 1000
        for label, folder, config, events in WORKFLOWS:
            run_dir = root / folder
            outdir = run_dir / label
            for sub in ("submit", "result", "data"):
                (outdir / sub).mkdir(parents=True, exist_ok=True)
            (run_dir / config).write_text(f"label = {label}\noutdir = {label}\n")
            (outdir / f"{label}_config_complete.ini").write_text("")
            (outdir / "submit" / f"dag_{label}.submit.dagman.out").write_text(dagman_out(4 * events))
            gps = "1126259462-4" if folder == "T1" else "1384782888-63"
            dag = []
            for event in range(events):
                for step, (kind, executable) in enumerate(KINDS):
                    name = f"{label}_data{event}_{gps}_{kind}"
                    log = f"{label}/log_{'data_generation' if step == 0 else 'data_analysis'}/{name}.log"
                    (run_dir / log).parent.mkdir(parents=True, exist_ok=True)
                    cluster += 1
                    (run_dir / log).write_text(job_log(cluster, BASE + timedelta(seconds=200 * step + 30 * event)))
                    (outdir / "submit" / f"{name}.submit").write_text(
                        f"universe = vanilla\nexecutable = /opt/dingo_env/bin/{executable}\n"
                        f"request_cpus = 8\nlog = {log}\narguments = $(ARGS)\nqueue\n"
                    )
                    dag.append(f"JOB {name}_arg_0 {label}/submit/{name}.submit")
                for suffix in ("_sampling.hdf5", "_importance_sampling.hdf5", "_importance_sampling_plot_corner.pdf"):
                    (outdir / "result" / f"{label}_data{event}_{gps}{suffix}").write_text(suffix)
                (outdir / "data" / f"{label}_data{event}_{gps}_generation_event_data.hdf5").write_text("")
            if psd_files:
                for ifo in ("H1", "L1"):
                    (outdir / "data" / f"{ifo}_psd.txt").write_text("")
            (outdir / "submit" / f"dag_{label}.submit").write_text("\n".join(dag) + "\n")
        (root / "run_metadata.txt").write_text("date: 2026-10-08T15:32:00Z\ncode: kailib-parallelisation at a4de31e\n")


def fake_result(path) -> dict:
    """Synthetic samples: Every run of a test draws from the same distributions."""
    path = Path(path)
    rng = np.random.default_rng(zlib.crc32(path.name.encode()))
    n = 2000
    samples = {"a": rng.normal(0, 1, n), "b": rng.normal(5, 2, n), "log_prob": rng.normal(-10, 30, n)}
    if path.name.endswith("_importance_sampling.hdf5"):
        samples.update(
            phase=rng.uniform(0, 2 * math.pi, n),
            weights=rng.uniform(0.5, 1.5, n),
            log_likelihood=rng.normal(size=n),
            log_prior=rng.normal(size=n),
        )
        base = REFERENCE_LOG_EVIDENCE if "T2" in path.name else -100.0
        return {"samples": samples, "log_evidence": base + 0.001 * (zlib.crc32(path.name.encode()) % 3)}
    return {"samples": samples, "log_evidence": None}


class TempDir(unittest.TestCase):
    def tempdir(self) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return Path(directory.name)


@needs_numpy
class TestStatistics(unittest.TestCase):
    def test_weighted_quantiles_with_equal_weights_match_numpy(self):
        values = np.random.default_rng(1).normal(size=1001)
        for q in (0.05, 0.5, 0.95):
            self.assertAlmostEqual(
                weighted_quantiles(values, np.ones_like(values), [q])[0],
                np.quantile(values, q, method="hazen"),
                places=12,
            )

    def test_weighted_quantiles_follow_the_weights(self):
        # Sample 0 holds a quarter of the weight, sample 1 three quarters.
        self.assertAlmostEqual(weighted_quantiles([0.0, 1.0], [1.0, 3.0], [0.5])[0], 0.75)

    def test_weighted_quantiles_ignore_zero_weights_and_non_finite_values(self):
        result = weighted_quantiles([1.0, 2.0, np.nan, 100.0], [1.0, 1.0, 1.0, 0.0], [0.5])
        self.assertAlmostEqual(result[0], 1.5)
        # A zero-weight sample between two others must not bend the interpolation:
        # Samples 1 and 3 sit at 1/8 and 5/8 of the weight, so 1/4 lies a quarter
        # of the way from 1 to 3.
        self.assertAlmostEqual(weighted_quantiles([1.0, 2.0, 3.0], [1.0, 0.0, 3.0], [0.25])[0], 1.5)

    def test_importance_summary_matches_dingos_formulas(self):
        summary = importance_summary([1.0, 1.0, 2.0])
        n_eff = 16 / 6
        self.assertAlmostEqual(summary["n_eff"], n_eff)
        self.assertAlmostEqual(summary["sample_efficiency"], n_eff / 3)
        self.assertAlmostEqual(summary["log_evidence_std"], math.sqrt((3 - n_eff) / (3 * n_eff)))
        equal = importance_summary(np.ones(10))
        self.assertAlmostEqual(equal["n_eff"], 10)
        self.assertAlmostEqual(equal["log_evidence_std"], 0.0)

    def runs(self, shift=0.0, n=5000):
        rng = np.random.default_rng(7)
        runs = {}
        for name in ("x", "y", "z"):
            runs[name] = {p: rng.normal(size=n) for p in ("p1", "p2", "p3", "p4")}
            runs[name]["log_prob"] = rng.normal(size=n) * (100 if name == "z" else 1)
        runs["z"]["p3"] = runs["z"]["p3"] + shift
        return runs

    def test_ks_passes_runs_from_the_same_distribution(self):
        result = ks_comparison(self.runs())
        self.assertTrue(result["passed"], result["worst"])
        self.assertEqual(result["tests"], 3 * 4)  # Three pairs, four parameters: log_prob is not one.
        self.assertAlmostEqual(result["threshold"], 0.01 / 12)
        self.assertEqual(result["identical_pairs"], [])

    def test_ks_fails_a_shifted_parameter(self):
        result = ks_comparison(self.runs(shift=0.2))
        self.assertFalse(result["passed"])
        self.assertEqual(result["worst"]["parameter"], "p3")
        self.assertIn("z", result["worst"]["pair"])

    def test_ks_reports_identical_runs(self):
        runs = self.runs()
        runs["y"] = dict(runs["x"])
        self.assertEqual(ks_comparison(runs)["identical_pairs"], [["x", "y"]])

    def test_ks_rejects_runs_with_different_parameters(self):
        runs = self.runs()
        del runs["y"]["p4"]
        with self.assertRaisesRegex(ValueError, "different parameters"):
            ks_comparison(runs)

    def test_evidence_comparison(self):
        agree = evidence_comparison({"x": (-100.0, 0.01), "y": (-100.02, 0.01), "ref": (-100.01, 0.0)})
        self.assertTrue(agree["passed"])
        self.assertAlmostEqual(agree["rows"][0]["z"], 0.02 / math.hypot(0.01, 0.01))
        disagree = evidence_comparison({"x": (-100.0, 0.01), "y": (-100.1, 0.01)})
        self.assertFalse(disagree["passed"])
        self.assertTrue(evidence_comparison({"x": (1.0, 0.0), "y": (1.0, 0.0)})["passed"])
        self.assertFalse(evidence_comparison({"x": (1.0, 0.0), "y": (2.0, 0.0)})["passed"])


@needs_numpy
class TestRunFolderChecks(TempDir):
    def test_result_files_tell_sampling_from_importance_sampling(self):
        directory = self.tempdir()
        names = [
            "T1b_data0_1126259462-4_sampling.hdf5",
            "T1b_data0_1126259462-4_importance_sampling.hdf5",
            "T1b_data0_1126259462-4_importance_sampling_plot_corner.pdf",
            "T1b_data1_1126259462-4_sampling.hdf5",
            "T1bx_data0_1126259462-4_sampling.hdf5",
            "notes.txt",
        ]
        for name in names:
            (directory / name).write_text("")
        files = result_files(directory, "T1b")
        self.assertEqual(sorted(files), [0, 1])
        self.assertEqual([p.name for p in files[0]["sampling"]], [names[0]])
        self.assertEqual([p.name for p in files[0]["importance_sampling"]], [names[1]])
        self.assertEqual([p.name for p in files[0]["corner"]], [names[2]])
        self.assertEqual(set(files[1]), {"sampling"})

    def test_completion(self):
        root = self.tempdir()
        RunRoot(root)
        outdir = root / "T1" / "T1b"
        self.assertTrue(completion(outdir, "T1b", 2)["passed"])
        (outdir / "result" / "T1b_data0_1126259462-5_sampling.hdf5").write_text("")
        self.assertIn("Event 0: 2 sampling file(s), expected 1", completion(outdir, "T1b", 2)["problems"])
        (outdir / "result" / "T1b_data1_1126259462-4_importance_sampling_plot_corner.pdf").unlink()
        self.assertIn("Event 1: 0 corner file(s), expected 1", completion(outdir, "T1b", 2)["problems"])
        (outdir / "submit" / "dag_T1b.submit.dagman.out").write_text(dagman_out(8, status=2))
        self.assertTrue(any("did not succeed" in p for p in completion(outdir, "T1b", 2)["problems"]))
        self.assertTrue(any("beyond the 1 listed" in p for p in completion(outdir, "T1b", 1)["problems"]))

    def test_shared_outputs_finds_files_every_chain_writes(self):
        root = self.tempdir()
        RunRoot(root)
        shared = shared_outputs(root / "T1" / "T1b", 2)
        self.assertEqual(shared["written_by_every_chain"], ["data/H1_psd.txt", "data/L1_psd.txt"])
        self.assertTrue(shared["same_outputs_per_event"])
        self.assertFalse(shared["passed"])
        # With one event, nothing is shared between chains.
        self.assertTrue(shared_outputs(root / "T1" / "T1a", 1)["passed"])

    def test_shared_outputs_passes_when_every_output_names_its_event(self):
        root = self.tempdir()
        RunRoot(root, psd_files=False)
        self.assertTrue(shared_outputs(root / "T2" / "T2b", 3)["passed"])

    def test_shared_outputs_fails_when_an_event_lacks_outputs(self):
        root = self.tempdir()
        RunRoot(root, psd_files=False)
        for path in (root / "T2" / "T2b").rglob("*_data2_*"):
            path.unlink()
        shared = shared_outputs(root / "T2" / "T2b", 3)
        self.assertEqual(shared["events_with_outputs"], [0, 1])
        self.assertFalse(shared["passed"])

    def test_workflow_timing(self):
        rows = [
            {"event": 0, "submitted": BASE, "finished": BASE + timedelta(seconds=100), "cpu_s": 360.0, "wasted_cpu_s": 0.0, "wait_s": 10.0},
            {"event": 1, "submitted": BASE + timedelta(seconds=50), "finished": BASE + timedelta(seconds=400), "cpu_s": 3600.0, "wasted_cpu_s": 36.0, "wait_s": 20.0},
        ]
        timing = workflow_timing(rows)
        self.assertEqual(timing["makespan_s"], 400)
        self.assertEqual(timing["chain_s"], {0: 100, 1: 350})
        self.assertAlmostEqual(timing["cpu_hours"], 1.1)
        self.assertAlmostEqual(timing["wasted_cpu_hours"], 0.01)
        rows[1]["finished"] = None
        self.assertEqual(workflow_timing(rows), {"complete": False})


@needs_numpy
class TestAnalyse(TempDir):
    def analyse(self, psd_files=True, reference=False):
        root = self.tempdir()
        RunRoot(root, psd_files=psd_files)
        reference_dir = None
        if reference:
            reference_dir = root / "reference"
            reference_dir.mkdir()
            (reference_dir / "label_data0_1384782888-63_sampling.hdf5").write_text("")
            (reference_dir / "label_data0_1384782888-63_importance_sampling.hdf5").write_text("")
        with mock.patch.object(analyse_results, "load_result", side_effect=fake_result):
            return analyse_results.analyse(root, reference_dir), root

    def verdicts(self, report):
        return {row["criterion"].split(" ")[0]: row for row in report["verdicts"]}

    def test_verdicts_on_a_good_run_with_shared_psd_files(self):
        report, _ = self.analyse()
        verdicts = self.verdicts(report)
        self.assertEqual(
            {key: row["passed"] for key, row in verdicts.items()},
            {"T1.1": True, "T1.2": False, "T1.3": True, "T2.1": True, "T2.2": True, "T2.3": True, "Also:": False},
        )
        self.assertIn("data/H1_psd.txt, data/L1_psd.txt", verdicts["T1.2"]["evidence"])
        self.assertIn("T1a 4 of 4 nodes done, T1b 8 of 8 nodes done", verdicts["T1.1"]["evidence"])
        self.assertIn("-5829.945", verdicts["T2.2"]["evidence"])

    def test_every_run_and_job_is_found(self):
        report, _ = self.analyse()
        self.assertEqual(report["tests"]["T1"]["network_ks"]["runs"], ["T1a", "T1b/0", "T1b/1"])
        self.assertEqual(report["tests"]["T2"]["network_ks"]["runs"], ["T2a", "T2b/0", "T2b/1", "T2b/2"])
        self.assertEqual(report["tests"]["T1"]["network_ks"]["parameters"], ["a", "b"])
        self.assertIn("phase", report["tests"]["T2"]["posteriors"])
        jobs = report["workflows"]["T2b"]["jobs"]
        self.assertEqual(len(jobs), 12)
        self.assertEqual({job["kind"] for job in jobs}, {"generation", "sampling", "importance sampling", "plot"})
        self.assertTrue(all(job["succeeded"] and job["cpu_s"] == 120 for job in jobs))
        # First submission: event 0's generation at BASE. Last finish: event 2's
        # plot, submitted 3 * 200 + 2 * 30 s later, running 140 s.
        self.assertEqual(report["workflows"]["T2b"]["timing"]["makespan_s"], 3 * 200 + 2 * 30 + 140)

    def test_a_disagreeing_log_evidence_fails_t2(self):
        def shifted(path):
            result = fake_result(path)
            if Path(path).name.startswith("T2b_data2_") and result["log_evidence"] is not None:
                result["log_evidence"] += 1.0
            return result

        root = self.tempdir()
        RunRoot(root)
        with mock.patch.object(analyse_results, "load_result", side_effect=shifted):
            report = analyse_results.analyse(root)
        self.assertFalse(self.verdicts(report)["T2.2"]["passed"])
        self.assertTrue(self.verdicts(report)["T1.3"]["passed"])

    def test_runs_that_agree_with_each_other_but_not_the_reference_fail_t2(self):
        def offset(path):
            result = fake_result(path)
            if Path(path).name.startswith("T2") and result["log_evidence"] is not None:
                result["log_evidence"] += 1.0
            return result

        root = self.tempdir()
        RunRoot(root)
        with mock.patch.object(analyse_results, "load_result", side_effect=offset):
            report = analyse_results.analyse(root)
        self.assertFalse(self.verdicts(report)["T2.2"]["passed"])
        failing = [row["pair"] for row in report["tests"]["T2"]["evidence"]["rows"] if not row["agree"]]
        self.assertEqual(sorted(pair[1] for pair in failing), ["Exercise 3"] * 4)

    def test_a_shifted_network_fails_t1(self):
        def shifted(path):
            result = fake_result(path)
            if Path(path).name.startswith("T1b_data1_") and Path(path).name.endswith("_sampling.hdf5"):
                result["samples"]["a"] = result["samples"]["a"] + 0.5
            return result

        root = self.tempdir()
        RunRoot(root)
        with mock.patch.object(analyse_results, "load_result", side_effect=shifted):
            report = analyse_results.analyse(root)
        self.assertFalse(self.verdicts(report)["T1.3"]["passed"])

    def test_few_effective_samples_skip_the_evidence_comparison(self):
        def lopsided(path):
            result = fake_result(path)
            if "T1" in Path(path).name and "weights" in result["samples"]:
                weights = np.full(len(result["samples"]["weights"]), 1e-6)
                weights[:10] = 1.0
                result["samples"]["weights"] = weights
                result["log_evidence"] += 5.0 if "T1b_data1_" in Path(path).name else 0.0
            return result

        root = self.tempdir()
        RunRoot(root)
        with mock.patch.object(analyse_results, "load_result", side_effect=lopsided):
            report = analyse_results.analyse(root)
        self.assertFalse(report["tests"]["T1"]["evidence_meaningful"])
        self.assertTrue(self.verdicts(report)["T1.3"]["passed"])
        self.assertIn("not compared", self.verdicts(report)["T1.3"]["evidence"])

    def test_the_references_own_network_samples_join_t2(self):
        report, _ = self.analyse(reference=True)
        self.assertEqual(report["tests"]["T2"]["network_ks_with_reference"]["runs"][-1], "reference")
        self.assertNotIn("network_ks_with_reference", report["tests"]["T1"])

    def test_the_report_renders_and_serialises(self):
        report, _ = self.analyse(psd_files=False)
        text = render_markdown(report)
        self.assertIn("| T1.2 No output file is written by more than one chain | PASS |", text)
        self.assertIn("| T2b/0 vs T2b/1 |", text)
        self.assertIn("Exercise 3 (reference) | -5829.945 | 0.014", text)
        self.assertIn("kailib-parallelisation at a4de31e", text)
        json.loads(json.dumps(to_json(report)))

    def test_main_writes_the_summary_and_copies_the_corner_plots(self):
        root = self.tempdir()
        RunRoot(root)
        output = root / "results"
        with mock.patch.object(analyse_results, "load_result", side_effect=fake_result), mock.patch("builtins.print"):
            analyse_results.main([str(root), str(output)])
        self.assertTrue((output / "summary.md").is_file())
        summary = json.loads((output / "summary.json").read_text())
        self.assertEqual(len(summary["verdicts"]), 7)
        self.assertEqual(len(list((output / "corner_plots").glob("*.pdf"))), 1 + 2 + 1 + 3)


class TestFormatting(unittest.TestCase):
    @needs_numpy
    def test_duration_and_json(self):
        self.assertEqual(duration(3725), "1:02:05")
        self.assertEqual(duration(None), "n/a")
        self.assertEqual(
            to_json({"t": BASE, "x": np.float64(1.5), "inf": math.inf, 1: [np.int64(2)]}),
            {"t": "2026-10-08 08:39:56", "x": 1.5, "inf": None, "1": [2]},
        )


if __name__ == "__main__":
    unittest.main()
